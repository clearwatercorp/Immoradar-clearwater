import json
from urllib.parse import quote

from scrapfly import ScrapeConfig

from config import CENTER_LAT, CENTER_LON, RADIUS_KM, PRICE_MAX, SURFACE_MIN, ROOMS_MIN


def search(client):
    if not client:
        return []
    filters = {
        "size": 24,
        "from": 0,
        "showAllModels": True,
        "filterType": "rent",
        "propertyType": ["house", "flat"],
        "newProperty": False,
        "page": 1,
        "resultsPerPage": 24,
        "sortBy": "relevance",
        "sortOrder": "desc",
        "onTheMarket": [True],
        "minSurfaceArea": SURFACE_MIN,
        "maxPrice": PRICE_MAX,
        "minRoomsQuantity": ROOMS_MIN,
        "center": {"lat": CENTER_LAT, "lon": CENTER_LON},
        "radius": RADIUS_KM,
    }
    url = "https://res.bienici.com/find?filters=" + quote(json.dumps(filters))

    try:
        result = client.scrape(ScrapeConfig(url=url, asp=True, country="fr"))
        print(f"[bienici] HTTP {result.upstream_status_code}")
        if result.upstream_status_code != 200:
            return []
        data = json.loads(result.content)
        ads = data.get("realEstateAds") or data.get("ads") or []
    except Exception as e:
        print(f"[bienici] erreur: {e}")
        return []

    return [parsed for a in ads if (parsed := parse_ad(a))]


def parse_ad(ad):
    try:
        photos = ad.get("photos") or []
        return {
            "id":      f"bienici-{ad.get('id')}",
            "source":  "Bien'ici",
            "titre":   ad.get("title") or ad.get("propertyType", "Location"),
            "desc":    ad.get("description", ""),
            "prix":    int(ad.get("price") or 0),
            "ville":   ad.get("city", ""),
            "surface": int(ad.get("surfaceArea") or 0),
            "pieces":  ad.get("roomsQuantity"),
            "lat":     ad.get("lat"),
            "lon":     ad.get("lon") or ad.get("lng"),
            "date":    ad.get("publicationDate", ""),
            "link":    f"https://www.bienici.com/annonce/{ad.get('id')}" if ad.get("id") else "",
            "image":   photos[0].get("url", "") if photos else "",
        }
    except Exception as e:
        print(f"[bienici] parse erreur: {e}")
        return None
