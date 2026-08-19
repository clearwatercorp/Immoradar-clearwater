import time
import threading

from flask import Flask, jsonify, send_file, request

import config
import storage
from scrapers import leboncoin, bienici, pap, seloger
from scrapers.common import passes_filters
from scrapers import diag
from strategies import location_saisonniere, marchand_de_biens

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


def enrich(ad):
    """Ajoute les scores des deux stratégies à une annonce brute."""
    ad = dict(ad)
    try:
        ad["loc_saisonniere"] = location_saisonniere.evaluate(ad)
    except Exception as e:
        ad["loc_saisonniere"] = None
        print(f"[scoring] location_saisonniere erreur sur {ad.get('id')}: {e}")
    try:
        ad["marchand_biens"] = marchand_de_biens.evaluate(ad)
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
    ads = [enrich(a) for a in ads]
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
    normalisees = [p for a in brutes if (p := _parse_api_ad(a))]
    kept = [a for a in normalisees if passes_filters(a)]
    new_ids = storage.upsert_ads(kept)

    _status["ts"] = time.time()
    _status["sources"] = dict(_status.get("sources") or {}, **{
        "Leboncoin": {"ok": True, "trouvees": len(brutes), "retenues": len(kept),
                      "detail": "importé depuis votre navigateur (bookmarklet)"}
    })
    print(f"[import] {len(brutes)} reçues → {len(kept)} retenues, {len(new_ids)} nouvelles")
    return _cors(jsonify({
        "ok": True,
        "recues": len(brutes),
        "retenues": len(kept),
        "nouvelles": len(new_ids),
        "count": len(storage.get_all_ads()),
    }))


def _cors(resp):
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Methods"] = "POST, OPTIONS"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return resp


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
        "credit_taux_annuel":     config.CREDIT_TAUX_ANNUEL,
        "credit_apport_pct":      config.CREDIT_APPORT_PCT,
        "credit_duree_ans":       config.CREDIT_DUREE_ANS,
        "location_saisonniere_surface_max": config.LOCATION_SAISONNIERE_SURFACE_MAX,
        "division_surface_min":   config.DIVISION_SURFACE_MIN,
        "travaux_cost_m2":        config.TRAVAUX_COST_M2,
        "refresh_min":            config.CACHE_TTL // 60,
        "proxy_actif":            bool(config.PROXY_URL),
        "scrapfly_actif":         bool(config.SCRAPFLY_KEY),
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
