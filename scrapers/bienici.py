"""Scraper Bien'ici — basé sur le module woob (modules/bienici), qui
révèle que l'endpoint réel est `www.bienici.com/realEstateAds.json`
(PAS `res.bienici.com/find` que j'avais deviné initialement), et que le
filtre géographique se fait par identifiants de zone (`zoneIdsByTypes`),
résolus via `res.bienici.com/suggest.json?q=<code postal>` — pas par
centre/rayon lat-lon.
"""

import json
from urllib.parse import quote

from scrapfly import ScrapeConfig

from config import PRICE_MAX_HARD_CAP
from zones import COMMUNES

SUGGEST_URL = "https://res.bienici.com/suggest.json?q={q}"
SEARCH_URL = "https://www.bienici.com/realEstateAds.json?filters="

_zone_ids_cache = {"ids": None}


def _resolve_zone_ids(client, force=False):
    if _zone_ids_cache["ids"] is not None and not force:
        return _zone_ids_cache["ids"]

    zone_ids = []
    for commune in COMMUNES:
        try:
            result = client.scrape(ScrapeConfig(url=SUGGEST_URL.format(q=commune["cp"]), asp=True, country="fr"))
            if result.upstream_status_code != 200:
                continue
            data = json.loads(result.content)
            items = data if isinstance(data, list) else data.get("suggestions") or data.get("results") or []
            for item in items:
                ids = item.get("zoneIds") or []
                if ids:
                    zone_ids.append(ids[0])
                    break
        except Exception as e:
            print(f"[bienici] erreur résolution zone {commune['nom']}: {e}")

    zone_ids = list(dict.fromkeys(zone_ids))  # dédoublonne en gardant l'ordre
    if zone_ids:
        _zone_ids_cache["ids"] = zone_ids
    return zone_ids


def search(client):
    if not client:
        return []

    zone_ids = _resolve_zone_ids(client)
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
    url = SEARCH_URL + quote(json.dumps(filters))

    try:
        result = client.scrape(ScrapeConfig(url=url, asp=True, country="fr"))
        print(f"[bienici] HTTP {result.upstream_status_code}")
        if result.upstream_status_code != 200:
            return []
        data = json.loads(result.content)
        ads = data.get("realEstateAds") or []
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
            "ville":     commune["nom"] if commune else "",
            "cp":        cp,
            "surface":   int(ad.get("surfaceArea") or 0),
            "pieces":    ad.get("roomsQuantity"),
            "type_bien": {"flat": "appartement", "house": "maison"}.get(ad.get("propertyType", ""), ad.get("propertyType", "")),
            "dpe":       ad.get("energyClassification"),
            "lat":       ad.get("lat"),
            "lon":       ad.get("lon") or ad.get("lng"),
            "date":      ad.get("publicationDate", ""),
            "link":      f"https://www.bienici.com/annonce/{ad.get('id')}" if ad.get("id") else "",
            "image":     photos[0].get("url", "") if photos else "",
        }
    except Exception as e:
        print(f"[bienici] parse erreur: {e}")
        return None
