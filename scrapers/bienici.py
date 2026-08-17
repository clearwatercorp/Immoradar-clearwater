"""Scraper Bien'ici — calqué sur le module woob (modules/bienici) :
endpoint `www.bienici.com/realEstateAds.json?filters=<json>`, filtre
géographique par `zoneIdsByTypes` dont les ids sont résolus via
`res.bienici.com/suggest.json?q=<code postal>`. Aucune protection
anti-bot particulière côté woob (PagesBrowser simple), donc `requests`
suffit.
"""

import json
from urllib.parse import quote

from config import PRICE_MAX_HARD_CAP
from zones import COMMUNES
from .http import get_session, TIMEOUT

SUGGEST_URL = "https://res.bienici.com/suggest.json?q={q}"
SEARCH_URL = "https://www.bienici.com/realEstateAds.json?filters="

_zone_ids_cache = {"ids": None}


def _resolve_zone_ids(force=False):
    if _zone_ids_cache["ids"] is not None and not force:
        return _zone_ids_cache["ids"]

    session = get_session()
    zone_ids = []
    for commune in COMMUNES:
        try:
            r = session.get(SUGGEST_URL.format(q=commune["cp"]), timeout=TIMEOUT)
            if r.status_code != 200:
                continue
            data = r.json()
            items = data if isinstance(data, list) else (data.get("suggestions") or data.get("results") or [])
            for item in items:
                ids = item.get("zoneIds") or []
                if ids:
                    zone_ids.append(ids[0])
                    break
        except Exception as e:
            print(f"[bienici] erreur résolution zone {commune['nom']}: {e}")

    zone_ids = list(dict.fromkeys(zone_ids))
    if zone_ids:
        _zone_ids_cache["ids"] = zone_ids
    return zone_ids


def search():
    zone_ids = _resolve_zone_ids()
    if not zone_ids:
        print("[bienici] aucune zone résolue — recherche annulée")
        return []

    filters = {
        "size": 100,
        "page": 1,
        "resultsPerPage": 24,
        "maxAuthorizedResults": 2400,
        "sortBy": "relevance",
        "sortOrder": "desc",
        "onTheMarket": [True],
        "showAllModels": False,
        "zoneIdsByTypes": {"zoneIds": zone_ids},
        "propertyType": ["house", "flat"],
        "filterType": "buy",
        "isNotLifeAnnuitySale": True,
        "maxPrice": PRICE_MAX_HARD_CAP,
    }

    try:
        r = get_session().get(
            SEARCH_URL + quote(json.dumps(filters)),
            headers={"accept": "application/json", "referer": "https://www.bienici.com/"},
            timeout=TIMEOUT,
        )
        print(f"[bienici] HTTP {r.status_code}")
        if r.status_code != 200:
            return []
        ads = r.json().get("realEstateAds") or []
    except Exception as e:
        print(f"[bienici] erreur: {e}")
        return []

    return [parsed for a in ads if (parsed := parse_ad(a))]


def parse_ad(ad):
    try:
        photos = ad.get("photos") or []
        cp = str(ad.get("postalCode") or "")
        commune = next((c for c in COMMUNES if c["cp"] == cp), None)
        return {
            "id":        f"bienici-{ad.get('id')}",
            "source":    "Bien'ici",
            "titre":     ad.get("title") or ad.get("propertyType", "Bien à vendre"),
            "desc":      ad.get("description", ""),
            "prix":      int(ad.get("price") or 0),
            "ville":     ad.get("city") or (commune["nom"] if commune else ""),
            "cp":        cp,
            "surface":   int(ad.get("surfaceArea") or 0),
            "pieces":    ad.get("roomsQuantity"),
            "type_bien": {"flat": "appartement", "house": "maison"}.get(
                ad.get("propertyType", ""), ad.get("propertyType", "")
            ),
            "dpe":       ad.get("energyClassification"),
            "lat":       ad.get("lat"),
            "lon":       ad.get("lon") or ad.get("lng"),
            "date":      ad.get("publicationDate", ""),
            "link":      f"https://www.bienici.com/annonce/{ad.get('id')}" if ad.get("id") else "",
            "image":     photos[0].get("url", "") if photos and isinstance(photos[0], dict) else "",
        }
    except Exception as e:
        print(f"[bienici] parse erreur: {e}")
        return None
