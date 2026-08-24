import time
import threading

from flask import Flask, jsonify, send_file, request

import config
import storage
from scrapers import leboncoin, bienici, pap, seloger
from scrapers.common import passes_filters
from scrapers import diag
from strategies import location_saisonniere, marchand_de_biens
from analysis import note_overrides

app = Flask(__name__)

_lock   = threading.Lock()
_status = {"ts": 0, "sources": {}, "running": False, "nouvelles": 0}

SCRAPERS = {
    "Leboncoin": leboncoin.search,
    "Bien'ici":  bienici.search,
    "PAP":       pap.search,
    "SeLoger":   seloger.search,
}

storage.init_db()


def refresh_cache():
    """Lance un cycle de scraping. Retourne False si un cycle est déjà en
    cours (les recherches ne s'empilent pas : le bouton « Actualiser » de
    l'interface peut être cliqué sans risque)."""
    if not _lock.acquire(blocking=False):
        print("[refresh] déjà en cours — demande ignorée")
        return False

    _status["running"] = True
    try:
        print("[refresh] Démarrage...")
        all_ads = []
        sources_status = {}
        for name, fn in SCRAPERS.items():
            try:
                ads = fn()
                kept = [a for a in ads if a and passes_filters(a)]
                sources_status[name] = {"ok": True, "trouvees": len(ads), "retenues": len(kept)}
                detail = diag.get_status(name)
                if detail:
                    sources_status[name].update(detail)
                elif ads and not kept:
                    sources_status[name]["detail"] = (
                        f"{len(ads)} annonces trouvées mais aucune dans la zone / les critères"
                    )
                all_ads.extend(kept)
                print(f"[{name}] {len(ads)} trouvées → {len(kept)} retenues après filtres")
            except Exception as e:
                sources_status[name] = {"ok": False, "error": str(e)}
                print(f"[{name}] erreur inattendue: {e}")

        new_ids = storage.upsert_ads(all_ads)
        _status["ts"] = time.time()
        _status["sources"] = sources_status
        _status["nouvelles"] = len(new_ids)
        print(f"[refresh] {len(all_ads)} annonces au total, {len(new_ids)} nouvelles")
    finally:
        _status["running"] = False
        _lock.release()
    return True


# Pas de rafraîchissement automatique : le scraping consomme des crédits
# (Scrapfly) et l'usage voulu est strictement « à la demande ». On ne scrape
# donc QUE sur clic « Rechercher » (route /api/refresh). Le serveur ne scrape
# rien au démarrage ni en tâche de fond.
print("[module] Scraping à la demande uniquement (pas de rafraîchissement auto).")


def _mediane_prix_m2(ads):
    """Médiane du prix/m² par (ville, nombre de pièces) sur tout le dataset —
    le « marché local » qui sert d'ancrage à l'attractivité et à la valeur de
    revente. On n'expose une médiane que si ≥ 3 comparables (sinon trop
    bruité)."""
    import statistics
    groupes = {}
    for a in ads:
        s = a.get("surface") or 0
        p = a.get("prix") or 0
        if s > 0 and p > 0:
            cle = ((a.get("ville") or "").strip().lower(), a.get("pieces"))
            groupes.setdefault(cle, []).append(p / s)
    return {cle: statistics.median(v) for cle, v in groupes.items() if len(v) >= 3}


def enrich(ad, marche=None):
    """Ajoute les scores des deux stratégies à une annonce brute. `marche` est
    la table des médianes prix/m² locales (cf. _mediane_prix_m2)."""
    # La note libre de l'utilisateur prime : elle peut corriger charges, loyer,
    # état/travaux, ou signaler un bien libre. On applique ces overrides avant
    # de scorer, et on les expose pour l'affichage.
    ad, _ov = note_overrides.apply_to_ad(ad)
    marche = marche or {}

    # Localisation pour la carte : coordonnées propres de l'annonce =
    # « précis » ; à défaut, on retombe sur le centre de la commune reconnue
    # (position APPROXIMATIVE, signalée par une bulle grise côté carte).
    from zones import match_commune
    lat, lon = ad.get("lat"), ad.get("lon")
    if lat is not None and lon is not None:
        ad["loc_precise"] = True
    else:
        commune = match_commune(ad.get("ville", ""), ad.get("cp", ""))
        if commune:
            ad["lat"], ad["lon"] = commune["lat"], commune["lon"]
        ad["loc_precise"] = False
    try:
        ad["loc_saisonniere"] = location_saisonniere.evaluate(ad, marche)
    except Exception as e:
        ad["loc_saisonniere"] = None
        print(f"[scoring] location_saisonniere erreur sur {ad.get('id')}: {e}")
    try:
        ad["marchand_biens"] = marchand_de_biens.evaluate(ad, marche)
    except Exception as e:
        ad["marchand_biens"] = None
        print(f"[scoring] marchand_de_biens erreur sur {ad.get('id')}: {e}")
    return ad


@app.route("/")
def index():
    return send_file("index.html")


@app.route("/bookmarklet")
def bookmarklet():
    return send_file("bookmarklet.html")


@app.route("/api/annonces")
def api_annonces():
    now = time.time()
    ads = storage.get_all_ads()
    for a in ads:
        a["nouveau"] = (now - a["first_seen"]) < config.NEW_WINDOW_H * 3600
    marche = _mediane_prix_m2(ads)
    ads = [enrich(a, marche) for a in ads]
    age_min = round((now - _status["ts"]) / 60, 1) if _status["ts"] else None
    return jsonify({
        "ok":          True,
        "count":       len(ads),
        "age_min":     age_min,
        "sources":     _status["sources"],
        "recherche_en_cours": _status["running"],
        "nouvelles":   _status["nouvelles"],
        "annonces":    ads,
    })


@app.route("/api/import", methods=["POST", "OPTIONS"])
def api_import():
    """Reçoit des annonces brutes envoyées par le bookmarklet depuis la
    session Leboncoin de l'utilisateur (son navigateur, son IP résidentielle,
    ses cookies — donc aucun blocage anti-robot). Appel cross-origin depuis
    leboncoin.fr, d'où les en-têtes CORS."""
    if request.method == "OPTIONS":
        return _cors(jsonify({}))

    try:
        payload = request.get_json(force=True, silent=True) or {}
    except Exception:
        payload = {}
    brutes = payload.get("ads") or []

    from scrapers.leboncoin import _parse_api_ad
    from scrapers.common import annotate_import

    normalisees = [p for a in brutes if (p := _parse_api_ad(a))]
    avec_desc = sum(1 for a in normalisees if (a.get("desc") or "").strip())
    kept, rejets, villes = [], {}, set()
    for a in normalisees:
        villes.add(a.get("ville") or "?")
        raison = annotate_import(a)   # souple : la zone est celle choisie sur Leboncoin
        if raison is None:
            kept.append(a)
        else:
            rejets[raison] = rejets.get(raison, 0) + 1
    new_ids = storage.upsert_ads(kept)

    _status["ts"] = time.time()
    _status["sources"] = dict(_status.get("sources") or {}, **{
        "Leboncoin": {"ok": True, "trouvees": len(brutes), "retenues": len(kept),
                      "detail": "importé depuis votre navigateur (bookmarklet)"}
    })
    print(f"[import] {len(brutes)} reçues, {len(normalisees)} lues → {len(kept)} retenues, "
          f"{len(new_ids)} nouvelles, rejets={rejets}")
    reponse = {
        "ok": True,
        "recues": len(brutes),
        "lues": len(normalisees),
        "avec_description": avec_desc,
        "retenues": len(kept),
        "nouvelles": len(new_ids),
        "rejets": rejets,               # {'sans_surface': 30, …}
        "villes": sorted(villes)[:8],   # échantillon de villes reçues
        "count": len(storage.get_all_ads()),
    }
    # Diagnostic : si rien n'est retenu, on renvoie les clés d'une annonce
    # brute pour repérer où sont réellement surface/ville dans ce format.
    if not kept and brutes:
        ex = brutes[0]
        reponse["debug"] = {
            "cles": sorted(ex.keys())[:40],
            "location_cles": sorted((ex.get("location") or {}).keys())[:20] if isinstance(ex.get("location"), dict) else None,
            "a_attributes": bool(ex.get("attributes")),
            "titre": (ex.get("subject") or ex.get("title") or "")[:80],
        }
    return _cors(reponse and jsonify(reponse))


def _cors(resp):
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Methods"] = "POST, OPTIONS"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return resp


@app.route("/api/clear", methods=["POST"])
def api_clear():
    """Efface toutes les annonces (pour repartir sur de nouveaux critères)."""
    storage.clear_all()
    _status["ts"] = 0
    _status["sources"] = {}
    _status["nouvelles"] = 0
    return jsonify({"ok": True})


@app.route("/api/favori", methods=["POST"])
def api_favori():
    """Marque/démarque une annonce comme favori. Les favoris sont préservés
    lors d'un « Vider »."""
    data = request.get_json(force=True, silent=True) or {}
    ad_id = data.get("id")
    if not ad_id:
        return jsonify({"ok": False, "erreur": "id manquant"}), 400
    ok = storage.set_favori(ad_id, bool(data.get("favori")))
    return jsonify({"ok": ok})


@app.route("/api/note", methods=["POST"])
def api_note():
    """Enregistre le suivi d'une annonce (statut + note libre). Persisté en
    base, préservé lors des ré-imports."""
    data = request.get_json(force=True, silent=True) or {}
    ad_id = data.get("id")
    if not ad_id:
        return jsonify({"ok": False, "erreur": "id manquant"}), 400
    ok = storage.set_note(ad_id, data.get("statut", ""), data.get("texte", ""))
    return jsonify({"ok": ok})


@app.route("/api/export")
def api_export():
    """Sauvegarde hors-ligne des biens suivis (favoris + notes) : un fichier
    JSON que l'utilisateur télécharge, indépendant du disque éphémère de
    l'hébergeur."""
    items = storage.export_saved()
    resp = jsonify({
        "version": 1,
        "type": "immoradar-favoris",
        "exported_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "count": len(items),
        "items": items,
    })
    resp.headers["Content-Disposition"] = "attachment; filename=immoradar-favoris.json"
    return resp


@app.route("/api/import-favoris", methods=["POST"])
def api_import_favoris():
    """Réinjecte un fichier de favoris/notes précédemment exporté."""
    data = request.get_json(force=True, silent=True) or {}
    items = data.get("items") if isinstance(data, dict) else data
    if not isinstance(items, list):
        return jsonify({"ok": False, "erreur": "format invalide (items manquant)"}), 400
    n = storage.import_saved(items)
    return jsonify({"ok": True, "importes": n})


@app.route("/api/refresh", methods=["POST"])
def api_refresh():
    """Déclenche une recherche à la demande, sans bloquer la requête HTTP
    (le scraping des 4 sites dépasse souvent le timeout d'un serveur web) :
    l'interface interroge ensuite /api/annonces pour suivre l'avancement."""
    if _status["running"]:
        return jsonify({"lancee": False, "en_cours": True})
    threading.Thread(target=refresh_cache, daemon=True).start()
    return jsonify({"lancee": True, "en_cours": True})


@app.route("/api/meta")
def api_meta():
    return jsonify({
        "center":                 {"lat": config.CENTER_LAT, "lon": config.CENTER_LON},
        "radius_km":              config.RADIUS_KM,
        "ville_centre":           config.VILLE_CENTRE,
        "price_min":              config.PRICE_MIN,
        "price_max_hard_cap":     config.PRICE_MAX_HARD_CAP,
        "notaire_pct":            config.NOTAIRE_PCT,
        "agence_revente_pct":     config.AGENCE_REVENTE_PCT,
        "lease_etudiant_mois":    config.LEASE_ETUDIANT_MOIS,
        "airbnb_mois":            config.AIRBNB_MOIS,
        "taux_occupation_airbnb": config.TAUX_OCCUPATION_AIRBNB,
        "airbnb_frais_pct":       config.AIRBNB_FRAIS_PCT,
        "credit_taux_annuel":     config.CREDIT_TAUX_ANNUEL,
        "credit_apport_pct":      config.CREDIT_APPORT_PCT,
        "credit_duree_ans":       config.CREDIT_DUREE_ANS,
        "location_saisonniere_surface_max": config.LOCATION_SAISONNIERE_SURFACE_MAX,
        "division_surface_min":   config.DIVISION_SURFACE_MIN,
        "travaux_cost_m2":        config.TRAVAUX_COST_M2,
        "refresh_min":            config.CACHE_TTL // 60,
        "proxy_actif":            bool(config.PROXY_URL),
        "scrapfly_actif":         bool(config.SCRAPFLY_KEY),
        "stockage_persistant":    storage.persistant(),
        "stockage_backend":       storage.storage_backend(),
    })


@app.route("/health")
def health():
    return jsonify({
        "status":  "ok",
        "cached":  len(storage.get_all_ads()),
        "sources": _status["sources"],
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=config.PORT)
