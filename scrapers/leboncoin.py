"""Scraper Leboncoin — structure calquée sur le module woob
(modules/leboncoin) :
  - catégorie "9" = Ventes immobilières, real_estate_type "1"=maison/"2"=appartement
  - la clé d'API n'est pas une constante : elle est extraite du JSON
    __NEXT_DATA__ de la page d'accueil (runtimeConfig.API.KEY) à chaque
    session, puis mise en cache et rafraîchie si l'API la rejette.
  - le filtre géographique se fait par liste de villes/codes postaux
    (filters.location.city_zipcodes), pas par rayon lat/lng.
  - attributes["real_estate_type"] est déjà un libellé texte.
"""

import json

from bs4 import BeautifulSoup

from config import PRICE_MAX_HARD_CAP
from zones import COMMUNES
from .http import get_session, TIMEOUT
from . import diag

SOURCE = "Leboncoin"

CATEGORY_VENTE = "9"
REAL_ESTATE_TYPES = ["1", "2"]  # maison, appartement
HOME_URL = "https://www.leboncoin.fr/annonces/offres"
API_URL = "https://api.leboncoin.fr/finder/search"

_api_key_cache = {"key": None}


def _fetch_api_key(force=False):
    if _api_key_cache["key"] and not force:
        return _api_key_cache["key"]
    try:
        r = get_session().get(HOME_URL, timeout=TIMEOUT)
        if r.status_code != 200:
            print(f"[leboncoin] page d'accueil HTTP {r.status_code} — clé API non récupérable")
            diag.set_status(SOURCE, f"Page d'accueil HTTP {r.status_code} — blocage anti-robot probable", bloque=True)
            return None
        tag = BeautifulSoup(r.text, "html.parser").find("script", id="__NEXT_DATA__")
        if not tag or not tag.string:
            print("[leboncoin] __NEXT_DATA__ introuvable sur la page d'accueil")
            diag.set_status(SOURCE, "Page d'accueil reçue mais __NEXT_DATA__ absent — page anti-robot ou structure changée", bloque=True)
            return None
        key = json.loads(tag.string).get("runtimeConfig", {}).get("API", {}).get("KEY")
        if key:
            _api_key_cache["key"] = key
        else:
            print("[leboncoin] clé API absente du __NEXT_DATA__")
            diag.set_status(SOURCE, "Clé d'API absente du __NEXT_DATA__ — structure du site changée")
        return key
    except Exception as e:
        print(f"[leboncoin] erreur récupération clé API: {e}")
        diag.set_status(SOURCE, f"Connexion impossible : {type(e).__name__}", bloque=True)
        return None


def _payload():
    return {
        "limit": 35,
        "limit_alu": 3,
        "sort_by": "time",
        "sort_order": "desc",
        "offset": 0,
        "extend": True,
        "listing_source": "direct-search",
        "filters": {
            "category": {"id": CATEGORY_VENTE},
            "location": {
                "city_zipcodes": [
                    {"city": c["nom"], "zipcode": c["cp"], "label": f"{c['nom']} {c['cp']}"} for c in COMMUNES
                ],
            },
            "enums": {"ad_type": ["offer"], "real_estate_type": REAL_ESTATE_TYPES},
            "ranges": {"price": {"max": PRICE_MAX_HARD_CAP}},
        },
    }


def _post_search(api_key):
    return get_session().post(
        API_URL,
        data=json.dumps(_payload()),
        headers={
            "api_key": api_key,
            "content-type": "application/json",
            "origin": "https://www.leboncoin.fr",
            "referer": "https://www.leboncoin.fr/recherche",
        },
        timeout=TIMEOUT,
    )


def search():
    diag.clear(SOURCE)
    api_key = _fetch_api_key()
    if not api_key:
        return []
    try:
        r = _post_search(api_key)
        if r.status_code in (401, 403):
            # clé peut-être expirée : une seule tentative de rafraîchissement
            api_key = _fetch_api_key(force=True)
            if not api_key:
                return []
            r = _post_search(api_key)

        print(f"[leboncoin] HTTP {r.status_code}")
        if r.status_code != 200:
            diag.set_status(SOURCE, f"API de recherche HTTP {r.status_code}", bloque=r.status_code in (401, 403, 429))
            return []
        ads = r.json().get("ads", [])
        if not ads:
            diag.set_status(SOURCE, "API OK mais aucune annonce renvoyée — filtres de recherche à vérifier")
    except Exception as e:
        print(f"[leboncoin] erreur: {e}")
        diag.set_status(SOURCE, f"Erreur de recherche : {type(e).__name__}", bloque=True)
        return []

    return [parsed for a in ads if (parsed := parse_ad(a))]


def parse_ad(ad):
    try:
        prix_list = ad.get("price") or [0]
        prix = prix_list[0] if prix_list else 0
        loc = ad.get("location", {}) or {}
        attrs = {a["key"]: a.get("value_label", a.get("value", "")) for a in ad.get("attributes", [])}

        try:
            surface = int(float(attrs.get("square", 0)))
        except (TypeError, ValueError):
            surface = 0

        try:
            pieces = int(attrs.get("rooms")) if attrs.get("rooms") else None
        except (TypeError, ValueError):
            pieces = None

        dpe_raw = (attrs.get("energy_rate") or "").strip()
        dpe = dpe_raw[0].upper() if dpe_raw and dpe_raw[0].isalpha() else None

        return {
            "id":        f"lbc-{ad.get('list_id')}",
            "source":    "Leboncoin",
            "titre":     ad.get("subject", ""),
            "desc":      ad.get("body", ""),
            "prix":      prix,
            "ville":     loc.get("city_label") or loc.get("city", ""),
            "cp":        loc.get("zipcode", ""),
            "surface":   surface,
            "pieces":    pieces,
            "type_bien": (attrs.get("real_estate_type") or "").lower(),
            "dpe":       dpe,
            "lat":       loc.get("lat"),
            "lon":       loc.get("lng"),
            "date":      ad.get("first_publication_date", ""),
            "link":      ad.get("url", f"https://www.leboncoin.fr/ventes_immobilieres/{ad.get('list_id')}.htm"),
            "image":     (ad.get("images") or {}).get("thumb_url", ""),
        }
    except Exception as e:
        print(f"[leboncoin] parse erreur: {e}")
        return None
