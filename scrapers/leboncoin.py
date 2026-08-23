"""Scraper Leboncoin — source prioritaire (de loin le plus gros volume).

Leboncoin est protégé par DataDome, qui filtre surtout sur l'empreinte TLS
et sur le fait de se présenter comme un navigateur web. La technique qui
passe gratuitement, documentée par la communauté et implémentée par la
bibliothèque open-source `lbc` (MIT, github.com/etienne-hd/lbc), est de se
faire passer non pas pour un navigateur mais pour l'**application mobile**
Leboncoin :

  - requêtes via curl_cffi (empreinte TLS/HTTP2 d'un vrai navigateur mobile) ;
  - User-Agent applicatif « LBC;iOS;18.x;iPhone;phone;<uuid>;wifi;101.x » ;
  - initialisation des cookies DataDome par une visite préalable de la home ;
  - sur 403, on ré-initialise entièrement la session (autre appareil, autres
    cookies) et on retente — DataDome est probabiliste, un nouvel essai passe
    souvent.

Cette API mobile (api.leboncoin.fr) est bien moins filtrée que le site web.

On s'appuie sur `lbc` comme moteur principal (maintenu : une mise à jour de
la lib suffit si Leboncoin change), avec repli sur une implémentation
curl_cffi interne si la lib est absente ou échoue.
"""

from urllib.parse import urlparse

from config import PRICE_MAX_HARD_CAP, CENTER_LAT, CENTER_LON, RADIUS_KM, VILLE_CENTRE, PROXY_URL
from .http import proxies_dict
from . import diag, fetch

SOURCE = "Leboncoin"

REAL_ESTATE_TYPES = ("1", "2")  # maison, appartement


def search():
    diag.clear(SOURCE)
    # En hébergement avec Scrapfly : l'API mobile passée par Scrapfly franchit
    # DataDome. C'est le chemin prioritaire dès qu'une clé est configurée.
    if fetch.enabled():
        return _search_via_scrapfly()
    # Sinon (usage local / résidentiel) : la lib lbc suffit.
    ads = _search_via_lbc()
    if ads is not None:
        return ads
    return _search_interne()


def _search_via_scrapfly():
    try:
        r = fetch.post(
            API_URL,
            json_body=_payload(),
            headers={"api_key": _CLE_API_PUBLIQUE},
            country="fr",
        )
        if r.status_code != 200:
            diag.set_status(SOURCE, f"API mobile via Scrapfly : HTTP {r.status_code}", bloque=r.status_code in (401, 403, 429))
            return []
        ads = r.json().get("ads", [])
        print(f"[leboncoin] Scrapfly → {len(ads)} annonces")
        if not ads:
            diag.set_status(SOURCE, "API mobile OK (Scrapfly) mais aucune annonce dans la zone/les critères")
        return [parsed for a in ads if (parsed := _parse_api_ad(a))]
    except Exception as e:
        print(f"[leboncoin] Scrapfly erreur: {e}")
        diag.set_status(SOURCE, f"Erreur via Scrapfly : {type(e).__name__}", bloque=True)
        return []


# Clé publique de l'appli mobile (historiquement stable). Utilisée uniquement
# via Scrapfly, où DataDome est franchi par le service.
_CLE_API_PUBLIQUE = "ba0c2dad52b3ec"


# ─── Moteur principal : bibliothèque lbc ──────────────────────────────────
def _lbc_proxy():
    """Convertit PROXY_URL en objet lbc.Proxy, ou None."""
    if not PROXY_URL:
        return None
    try:
        import lbc
        p = urlparse(PROXY_URL)
        return lbc.Proxy(
            host=p.hostname, port=p.port or 80,
            username=p.username, password=p.password,
            scheme=p.scheme or "http",
        )
    except Exception as e:
        print(f"[leboncoin] PROXY_URL invalide ({e}), ignoré")
        return None


def _search_via_lbc():
    """Retourne la liste d'annonces, ou None si la lib n'est pas utilisable
    (dans ce cas on tente le moteur interne). Une liste vide = la lib a
    répondu mais sans résultat / bloquée : on ne tente pas le repli, il
    utiliserait la même technique."""
    try:
        import lbc
    except Exception as e:
        print(f"[leboncoin] lib lbc indisponible ({e}) — repli interne")
        return None

    try:
        client = lbc.Client(proxy=_lbc_proxy())
        location = lbc.City(lat=CENTER_LAT, lng=CENTER_LON, radius=int(RADIUS_KM * 1000), city=VILLE_CENTRE)
        result = client.search(
            locations=[location],
            category=lbc.Category.IMMOBILIER_VENTES_IMMOBILIERES,
            sort=lbc.Sort.NEWEST,
            limit=35,
            real_estate_type=REAL_ESTATE_TYPES,
            price=(0, PRICE_MAX_HARD_CAP),
        )
        ads = [parsed for a in result.ads if (parsed := _parse_lbc_ad(a))]
        print(f"[leboncoin] lbc → {len(result.ads)} annonces, {len(ads)} exploitables")
        if not ads:
            diag.set_status(SOURCE, "API mobile OK mais aucune annonce dans la zone/les critères")
        return ads
    except Exception as e:
        nom = type(e).__name__
        # DatadomeError = blocage après tous les retries de la lib.
        if "Datadome" in nom:
            print("[leboncoin] lbc bloqué par DataDome après retries")
            diag.set_status(SOURCE, "Bloqué par DataDome (API mobile) malgré plusieurs tentatives", bloque=True)
            return []
        print(f"[leboncoin] lbc erreur {nom}: {e} — repli interne")
        return None


def _lbc_attr(ad, key):
    attr = (ad.attributes or {}).get(key)
    return attr.value_label if attr else None


def _parse_lbc_ad(ad):
    try:
        loc = ad.location

        surface = 0
        try:
            surface = int(float(_lbc_attr(ad, "square") or 0))
        except (TypeError, ValueError):
            pass

        pieces = None
        try:
            rooms = _lbc_attr(ad, "rooms")
            pieces = int(rooms) if rooms else None
        except (TypeError, ValueError):
            pass

        dpe_raw = (_lbc_attr(ad, "energy_rate") or "").strip()
        dpe = dpe_raw[0].upper() if dpe_raw and dpe_raw[0].isalpha() else None

        images = ad.images or []

        return {
            "id":        f"lbc-{ad.id}",
            "source":    SOURCE,
            "titre":     ad.subject or "",
            "desc":      ad.body or "",
            "prix":      int(ad.price or 0),
            "ville":     getattr(loc, "city_label", None) or getattr(loc, "city", "") or "",
            "cp":        getattr(loc, "zipcode", "") or "",
            "surface":   surface,
            "pieces":    pieces,
            "type_bien": (_lbc_attr(ad, "real_estate_type") or "").lower(),
            "dpe":       dpe,
            "lat":       getattr(loc, "lat", None),
            "lon":       getattr(loc, "lng", None),
            "date":      ad.first_publication_date or "",
            "link":      ad.url or f"https://www.leboncoin.fr/ventes_immobilieres/{ad.id}.htm",
            "image":     images[0] if images else "",
        }
    except Exception as e:
        print(f"[leboncoin] parse lbc erreur: {e}")
        return None


# ─── Repli interne : curl_cffi + User-Agent appli mobile ──────────────────
# Reproduit la même technique que lbc, en autonome, pour le cas où la lib
# n'est pas installée sur l'hébergeur.
import json      # noqa: E402
import random    # noqa: E402
import uuid      # noqa: E402

API_URL = "https://api.leboncoin.fr/finder/search"
HOME_URL = "https://www.leboncoin.fr/"


def _user_agent_mobile():
    ios = random.choice([True, True, False])
    if ios:
        ver = random.choice(["18.3", "18.4", "18.5", "18.6", "26.0", "26.1"])
        app = random.choice(["101.44.0", "101.43.1", "101.42.0", "101.45.0"])
        return f"LBC;iOS;{ver};iPhone;phone;{uuid.uuid4()};wifi;{app}"
    ver = random.choice(["12", "13", "14", "15"])
    model = random.choice(["Pixel 7", "Pixel 8", "SM-G991B", "SM-S918B", "Redmi Note 12"])
    app = random.choice(["100.85.2", "100.84.1", "100.83.1"])
    return f"LBC;Android;{ver};{model};phone;{uuid.uuid4().hex[:16]};wifi;{app}"


def _payload():
    return {
        "filters": {
            "category": {"id": "9"},
            "enums": {"ad_type": ["offer"], "real_estate_type": list(REAL_ESTATE_TYPES)},
            "keywords": {"text": None},
            "location": {"locations": [{
                "locationType": "city",
                "city": VILLE_CENTRE,
                "label": f"{VILLE_CENTRE} (toute la ville)",
                "area": {"lat": CENTER_LAT, "lng": CENTER_LON, "radius": int(RADIUS_KM * 1000)},
            }]},
            "ranges": {"price": {"min": 0, "max": PRICE_MAX_HARD_CAP}},
        },
        "limit": 35, "limit_alu": 3, "offset": 0,
        "disable_total": True, "extend": True, "listing_source": "direct-search",
        "sort_by": "time", "sort_order": "desc",
    }


def _nouvelle_session():
    try:
        from curl_cffi import requests as cffi
    except Exception as e:
        print(f"[leboncoin] curl_cffi absent ({e}) — repli impossible")
        return None
    navigateur = random.choice(["safari_ios", "chrome_android", "safari", "firefox"])
    s = cffi.Session(impersonate=navigateur)
    if PROXY_URL:
        s.proxies = proxies_dict()
    s.headers.update({
        "User-Agent": _user_agent_mobile(),
        "Sec-Fetch-Dest": "empty", "Sec-Fetch-Mode": "cors", "Sec-Fetch-Site": "same-site",
    })
    try:
        s.get(HOME_URL, timeout=30)  # amorce les cookies DataDome
    except Exception:
        pass
    return s


def _search_interne(max_essais=4):
    dernier = None
    for essai in range(1, max_essais + 1):
        session = _nouvelle_session()
        if session is None:
            diag.set_status(SOURCE, "Ni la lib lbc ni curl_cffi ne sont installés", bloque=False)
            return []
        try:
            r = session.post(API_URL, json=_payload(), timeout=30)
            if r.status_code == 200:
                ads = r.json().get("ads", [])
                print(f"[leboncoin] repli interne (essai {essai}) → {len(ads)} annonces")
                if not ads:
                    diag.set_status(SOURCE, "API mobile OK mais aucune annonce dans la zone/les critères")
                return [parsed for a in ads if (parsed := _parse_api_ad(a))]
            dernier = f"HTTP {r.status_code}"
            print(f"[leboncoin] repli interne (essai {essai}) → {dernier}, nouvelle session")
        except Exception as e:
            dernier = f"injoignable ({type(e).__name__})"
            print(f"[leboncoin] repli interne (essai {essai}) → {dernier}")

    diag.set_status(SOURCE, f"Bloqué après {max_essais} tentatives (dernier : {dernier})", bloque=True)
    return []


import re as _re


def _to_int(v):
    try:
        # Espaces (y compris insécables) = séparateurs de milliers en français ;
        # virgule = séparateur décimal. « 7 800 » → 7800, « 45,5 » → 45.
        s = str(v).replace(" ", "").replace(" ", "").replace(" ", "").replace(",", ".")
        return int(float(s))
    except (TypeError, ValueError):
        return 0


# Mots qui, juste avant un « X m² », désignent une surface AUTRE que la
# surface habitable (jardin, terrain…) — à ne pas confondre avec elle.
_SURFACE_HORS_SUJET = (
    "jardin", "terrain", "parcelle", "terrasse", "balcon", "cave", "garage",
    "cour", "piscine", "cellier", "grenier", "combles", "sous-sol", "sous sol",
    "dépendance", "dependance", "loggia", "box", "parking", "champ", "prairie",
)
_SURFACE_RE = _re.compile(r"(\d{2,4})\s*m(?:²|2|²)", _re.I)


# --- Périodicité d'un montant (annuel / trimestriel / mensuel) --------------
# On la déduit du fragment de texte entourant le montant, qu'elle soit
# annoncée AVANT (« loyer annuel de 4 936 € ») ou APRÈS (« 4 800 €/an »).
_PER_TRIMESTRE = _re.compile(r"trimestr", _re.I)
_PER_ANNUEL = _re.compile(r"annuel|annuelle|/\s*an\b|par\s+an\b|à\s+l['’]?\s*ann[ée]e|a\s+l['’]?\s*annee|\bh\.?t\.?\s*/?\s*an\b", _re.I)
_PER_MENSUEL = _re.compile(r"mensuel|mensuelle|/\s*mois|par\s+mois|\bmois\b|\bcc\s*/\s*mois\b", _re.I)


def _periode_diviseur(fragment, defaut_annuel_si_gros=None):
    """Diviseur pour ramener un montant au mois : 12 (annuel), 3 (trimestriel),
    1 (mensuel). Si la périodicité n'est pas explicite et qu'un seuil est
    fourni, un montant >= seuil est traité comme annuel."""
    f = fragment or ""
    if _PER_TRIMESTRE.search(f):
        return 3
    a = _PER_ANNUEL.search(f)
    mth = _PER_MENSUEL.search(f)
    if a and not mth:
        return 12
    if mth and not a:
        return 1
    if a and mth:
        # Les deux apparaissent : on tranche par la plus proche du montant.
        return 12 if a.start() > mth.start() else 1
    return None  # inconnue


# Charges de copropriété. On cherche un montant proche du mot « charges »,
# en EXCLUANT l'énergie (« dépenses annuelles d'énergie » du DPE) et les
# tournures où « charges » qualifie un LOYER (« hors charges », « charges
# comprises ») — là le montant est un loyer, pas des charges de copro.
# Le montant peut être suivi de « € » ou du mot « euros » (« 762 euros »).
_EUR = r"(?:€|euros?|eur\b)"
# Un montant : soit des milliers correctement groupés par 3 (« 4 800 »,
# « 1 784 », « 1.200 »), soit un nombre simple d'au plus 7 chiffres, avec
# éventuelle décimale. IMPORTANT : n'autorise PAS « 2028 614 » (année + loyer
# accolés) à être lu comme « 2 028 614 » — sinon un loyer de 614 € devient
# 2 millions. Les espaces insécables/fines de Leboncoin sont pris en compte.
_AMOUNT = r"(?<![\d.,])((?:\d{1,3}(?:[   .]\d{3})+|\d{1,7})(?:,\d{1,2})?)"
_CHARGES_RE = _re.compile(
    rf"charges?[^.\n€]{{0,70}}?{_AMOUNT}\s*{_EUR}\s*"
    r"(par\s+an|/\s*an|annuel\w*|par\s+trimestre|trimestriel\w*|par\s+mois|/\s*mois|mensuel\w*)?",
    _re.I,
)
_ENERGIE_MOTS = ("énerg", "energ", "chauffage", "électric", "electric", "consommation", "kwh", "gaz")
# Tournures où « charges » qualifie le loyer, pas un montant de charges de copro.
_CHARGES_LOYER = ("hors charge", "hors charges", "charges comprises", "charges incluses",
                  "cc", "c.c", "charge comprise")


def _extract_charges_mensuelles(titre, desc):
    """Charges de copropriété ramenées au mois, ou None. Ignore l'énergie et
    les tournures « hors charges / charges comprises » (qui portent sur le
    loyer)."""
    texte = f"{titre or ''} {desc or ''}"
    for m in _CHARGES_RE.finditer(texte):
        avant = texte[max(0, m.start() - 20):m.start() + 8].lower()
        contexte = texte[max(0, m.start() - 20):m.end() + 20].lower()
        if any(mot in contexte for mot in _ENERGIE_MOTS):
            continue  # dépense d'énergie, pas des charges de copropriété
        if any(mot in avant for mot in _CHARGES_LOYER):
            continue  # « hors charges … » / « charges comprises … » = loyer
        montant = _to_int(m.group(1))
        if montant <= 0:
            continue
        div = _periode_diviseur(m.group(0))
        if div is None:
            # Périodicité non précisée : un montant élevé est presque toujours
            # annuel (des charges mensuelles dépassent rarement ~500 €).
            div = 12 if montant >= 600 else 1
        return round(montant / div)
    return None


# Loyer réel : on n'accepte QUE les mentions attestant un loyer effectif
# (bien loué / locataire en place / loyer garanti / revenu locatif), pas une
# estimation du vendeur — sinon on écraserait à tort l'estimation de marché.
_LOYER_RE = _re.compile(
    r"(?:lou[ée]e?s?|locataires?|loyers?\s+(?:actuel\w*|per[çc]u\w*|mensuel\w*|annuel\w*|"
    r"garanti\w*|en\s+cours|net\w*|hors\s+charges?)|revenus?\s+locatifs?|rapporte\w*|"
    r"bail\s+en\s+cours|d[ée]j[àa]\s+lou[ée])"
    rf"[^.\n€]{{0,45}}?{_AMOUNT}\s*{_EUR}\s*"
    r"(/?\s*mois|par\s+mois|mensuel\w*|/?\s*an|annuel\w*|par\s+an|hors\s+charges?|cc)?",
    _re.I,
)
# Marqueurs d'une simple ESTIMATION (à ne pas prendre pour un loyer réel).
_LOYER_ESTIME = ("estimation", "estimé", "estime", "potentiel", "de marché", "de marche",
                 "pourrait", "envisageable", "possibilité de lou", "possibilite de lou",
                 "peut être lou", "peut etre lou", "à prévoir", "a prevoir")


def _extract_loyer_reel(titre, desc, prix=0):
    """Loyer mensuel réel indiqué dans l'annonce (bien occupé / loyer garanti),
    à utiliser plutôt que l'estimation de marché, ou None.

    Robustesse : on écarte les estimations, on REJETTE tout montant proche du
    prix de vente (un ancrage « LOUE … 268 000 € » ne doit pas être pris pour
    un loyer), et on PRÉFÈRE les montants explicitement étiquetés « loyer … »
    (ex. « Loyer hors charges : 759 € ») à un simple « loué » suivi d'un
    montant lointain."""
    texte = f"{titre or ''} {desc or ''}"
    seuil_prix = (prix or 0) * 0.5   # un loyer (mensuel ou annuel) n'est jamais la moitié du prix
    meilleur = None      # (score, valeur_mensuelle)
    for m in _LOYER_RE.finditer(texte):
        montant = _to_int(m.group(1))
        if montant < 100:
            continue
        if seuil_prix and montant >= seuil_prix:
            continue  # c'est le prix de vente (ou un autre gros montant), pas un loyer
        contexte = texte[max(0, m.start() - 30):m.end() + 5].lower()
        if any(mot in contexte for mot in _LOYER_ESTIME):
            continue  # estimation, pas un loyer effectif
        div = _periode_diviseur(m.group(0))
        if div is None:
            div = 12 if montant > 5000 else 1
        valeur = round(montant / div)
        if valeur < 100 or valeur > 8000:
            continue  # loyer mensuel implausible (garde-fou)
        # Un libellé « loyer … » est bien plus fiable qu'un simple « loué ».
        score = 2 if "loyer" in m.group(0).lower() else 1
        if meilleur is None or score > meilleur[0]:
            meilleur = (score, valeur)
        if score == 2:
            break  # étiquette explicite : on ne cherche pas mieux
    return meilleur[1] if meilleur else None


def _extract_surface(titre, desc, attrs):
    """Surface HABITABLE. Ordre : attribut structuré, puis le titre (qui
    porte quasi toujours la surface habitable sur Leboncoin), puis la
    description en écartant les « m² » de jardin/terrain/terrasse/etc.
    (sinon on prend « jardin de 200 m² » pour un bien de 70 m²)."""
    s = _to_int(attrs.get("square") or attrs.get("surface"))
    if s:
        return s

    m = _SURFACE_RE.search(titre or "")
    if m:
        return _to_int(m.group(1))

    for m in _SURFACE_RE.finditer(desc or ""):
        avant = (desc[max(0, m.start() - 22):m.start()]).lower()
        if any(mot in avant for mot in _SURFACE_HORS_SUJET):
            continue
        return _to_int(m.group(1))
    return 0


def _parse_api_ad(ad):
    """Normalise une annonce Leboncoin. Défensif : le format des annonces
    embarquées dans les pages (__NEXT_DATA__) varie et n'a pas toujours le
    même schéma que l'API mobile. On cherche donc chaque donnée à plusieurs
    endroits, avec repli sur une extraction depuis le titre."""
    try:
        # Prix : liste [n] ou nombre, ou champ price_cents.
        prix = 0
        pr = ad.get("price")
        if isinstance(pr, list) and pr:
            prix = _to_int(pr[0])
        elif isinstance(pr, (int, float, str)):
            prix = _to_int(pr)
        if not prix and ad.get("price_cents"):
            prix = _to_int(ad["price_cents"]) // 100

        loc = ad.get("location", {}) or {}

        # Attributs : liste [{key,value,value_label}] → dict par clé (souvent
        # absents dans les pages de liste, d'où les replis ci-dessous).
        attrs = {}
        for a in (ad.get("attributes") or []):
            if isinstance(a, dict) and a.get("key"):
                attrs[a["key"]] = a.get("value_label") or a.get("value") or ""

        titre = ad.get("subject") or ad.get("title") or ""
        desc = ad.get("body") or ad.get("description") or ""
        texte = f"{titre} {desc}"

        # Surface habitable (évite les m² de jardin/terrain, cf. _extract_surface).
        surface = _extract_surface(titre, desc, attrs)
        if not surface:
            surface = _to_int(ad.get("square") or ad.get("surface"))

        # Pièces : attribut rooms, sinon titre (« T3 », « 3 pièces »).
        pieces = _to_int(attrs.get("rooms") or ad.get("rooms")) or None
        if not pieces:
            m = _re.search(r"\b[TFtf]\s?([1-9])\b|\b([1-9])\s*pi[eè]ces?\b", texte)
            if m:
                pieces = _to_int(m.group(1) or m.group(2)) or None

        dpe_raw = (attrs.get("energy_rate") or ad.get("energy_rate") or "").strip()
        dpe = dpe_raw[0].upper() if dpe_raw and dpe_raw[0].isalpha() else None

        # Type de bien : attribut, sinon déduit du titre.
        type_bien = (attrs.get("real_estate_type") or "").lower()
        if type_bien in ("1", "maison"):
            type_bien = "maison"
        elif type_bien in ("2", "appartement"):
            type_bien = "appartement"
        elif not type_bien:
            low = texte.lower()
            if "maison" in low or "villa" in low:
                type_bien = "maison"
            elif "appartement" in low or _re.search(r"\b[TFtf]\s?[1-9]\b", texte):
                type_bien = "appartement"

        # Ville / CP : plusieurs schémas possibles.
        ville = (loc.get("city_label") or loc.get("city") or loc.get("city_name")
                 or ad.get("city_label") or ad.get("city") or "")
        cp = str(loc.get("zipcode") or loc.get("zip_code") or ad.get("zipcode") or "")
        lat = loc.get("lat") if loc.get("lat") is not None else ad.get("lat")
        lon = (loc.get("lng") if loc.get("lng") is not None
               else loc.get("lon") if loc.get("lon") is not None else ad.get("lng"))

        images = ad.get("images") or {}
        image = ""
        if isinstance(images, dict):
            image = images.get("thumb_url") or (images.get("urls") or [""])[0] if images.get("urls") else images.get("thumb_url", "")
        elif isinstance(images, list) and images:
            image = images[0] if isinstance(images[0], str) else (images[0].get("url", "") if isinstance(images[0], dict) else "")

        list_id = ad.get("list_id") or ad.get("id")

        return {
            "id":        f"lbc-{list_id}",
            "source":    SOURCE,
            "titre":     titre,
            "desc":      desc,
            "prix":      prix,
            "ville":     ville,
            "cp":        cp,
            "surface":   surface,
            "pieces":    pieces,
            "type_bien": type_bien,
            "charges_mensuelles": _extract_charges_mensuelles(titre, desc),
            "loyer_reel":          _extract_loyer_reel(titre, desc, prix),
            "dpe":       dpe,
            "lat":       lat,
            "lon":       lon,
            "date":      ad.get("first_publication_date") or ad.get("index_date") or "",
            "link":      ad.get("url") or f"https://www.leboncoin.fr/ventes_immobilieres/{list_id}.htm",
            "image":     image,
        }
    except Exception as e:
        print(f"[leboncoin] parse api erreur: {e}")
        return None
