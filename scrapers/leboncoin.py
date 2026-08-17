"""Scraper Leboncoin — basé sur le module woob (github.com/woob-project/woob,
modules/leboncoin), qui confirme :
  - catégorie "9" = Ventes immobilières, real_estate_type "1"=maison/"2"=appartement
  - la clé d'API n'est PAS une constante : elle est extraite du JSON
    __NEXT_DATA__ de la page d'accueil (runtimeConfig.API.KEY) à chaque
    session, d'où _fetch_api_key() ci-dessous (mise en cache mémoire,
    rafraîchie si le call échoue).
  - le filtre géographique se fait par liste de villes/codes postaux
    (filters.location.city_zipcodes), PAS par rayon lat/lng — d'où
    l'usage de zones.COMMUNES au lieu d'un filtre "area".
  - attributes["real_estate_type"] est déjà un libellé texte ("Appartement"/
    "Maison"), pas un code numérique.
"""

import json

from scrapfly import ScrapeConfig

from config import PRICE_MAX_HARD_CAP
from zones import COMMUNES

CATEGORY_VENTE = "9"
REAL_ESTATE_TYPES = ["1", "2"]  # maison, appartement
HOME_URL = "https://www.leboncoin.fr/annonces/offres"
API_URL = "https://api.leboncoin.fr/finder/search"

_HEADERS_BASE = {
    "accept": "*/*",
    "accept-language": "fr-FR,fr;q=0.9",
    "content-type": "application/json",
    "origin": "https://www.leboncoin.fr",
    "referer": "https://www.leboncoin.fr/recherche",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
}

_api_key_cache = {"key": None}


def _fetch_api_key(client, force=False):
    if _api_key_cache["key"] and not force:
        return _api_key_cache["key"]
    try:
        result = client.scrape(ScrapeConfig(url=HOME_URL, asp=True, country="fr"))
        if result.upstream_status_code != 200:
            print(f"[leboncoin] impossible de récupérer la clé API, HTTP {result.upstream_status_code}")
            return None
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(result.content, "html.parser")
        tag = soup.find("script", id="__NEXT_DATA__")
        if not tag or not tag.string:
            print("[leboncoin] __NEXT_DATA__ introuvable sur la page d'accueil")
            return None
        data = json.loads(tag.string)
        key = data.get("runtimeConfig", {}).get("API", {}).get("KEY")
        if key:
            _api_key_cache["key"] = key
        return key
    except Exception as e:
        print(f"[leboncoin] erreur récupération clé API: {e}")
        return None


def _build_payload():
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
            "enums": {
                "ad_type": ["offer"],
                "real_estate_type": REAL_ESTATE_TYPES,
            },
            "ranges": {
                "price": {"max": PRICE_MAX_HARD_CAP},
            },
        },
    }


def _do_search(client, api_key):
    headers = dict(_HEADERS_BASE, api_key=api_key)
    return client.scrape(ScrapeConfig(
        url=API_URL,
        method="POST",
        data=json.dumps(_build_payload()),
        headers=headers,
        asp=True,
        country="fr",
    ))


def search(client):
    if not client:
        return []

    api_key = _fetch_api_key(client)
    if not api_key:
        return []

    try:
        result = _do_search(client, api_key)
        if result.upstream_status_code in (401, 403):
            # clé potentiellement expirée : on la rafraîchit une fois
            api_key = _fetch_api_key(client, force=True)
            if not api_key:
                return []
            result = _do_search(client, api_key)

        print(f"[leboncoin] HTTP {result.upstream_status_code}")
        if result.upstream_status_code != 200:
            return []
        ads = json.loads(result.content).get("ads", [])
    except Exception as e:
        print(f"[leboncoin] erreur: {e}")
        return []

    return [parsed for a in ads if (parsed := parse_ad(a))]


def parse_ad(ad):
    try:
        prix_list = ad.get("price", [0])
        prix = prix_list[0] if prix_list else 0
        loc = ad.get("location", {}) or {}
        attrs = {a["key"]: a.get("value_label", a.get("value", "")) for a in ad.get("attributes", [])}

        surface = 0
        try:
            surface = int(float(attrs.get("square", 0)))
        except (TypeError, ValueError):
            pass

        pieces = None
        try:
            pieces = int(attrs.get("rooms")) if attrs.get("rooms") else None
        except (TypeError, ValueError):
            pass

        dpe_raw = (attrs.get("energy_rate") or "").strip()
        dpe = dpe_raw[0].upper() if dpe_raw and dpe_raw[0].isalpha() else None

        type_bien = (attrs.get("real_estate_type") or "").lower()

        return {
            "id":        f"lbc-{ad.get('list_id')}",
            "source":    "Leboncoin",
            "titre":     ad.get("subject", ""),
            "desc":      ad.get("body", ""),
            "prix":      prix,
            "ville":     loc.get("city_label", loc.get("city", "")),
            "cp":        loc.get("zipcode", ""),
            "surface":   surface,
            "pieces":    pieces,
            "type_bien": type_bien,
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
