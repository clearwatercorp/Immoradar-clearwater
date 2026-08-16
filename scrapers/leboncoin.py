import json

from scrapfly import ScrapeConfig

from config import CENTER_LAT, CENTER_LON, RADIUS_KM, PRICE_MAX_HARD_CAP

CATEGORY_VENTE = "9"            # "Ventes immobilières" (catégorie immobilier LBC)
REAL_ESTATE_TYPES = ["1", "2"]  # maison, appartement
TYPE_LABELS = {"1": "maison", "2": "appartement"}


def search(client):
    if not client:
        return []
    headers = {
        "accept": "*/*",
        "accept-language": "fr-FR,fr;q=0.9",
        "api_key": "ba0c2dad52b3ec",
        "content-type": "application/json",
        "origin": "https://www.leboncoin.fr",
        "referer": "https://www.leboncoin.fr/recherche",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    }
    payload = {
        "limit": 35,
        "limit_alu": 0,
        "sort_by": "time",
        "sort_order": "desc",
        "offset": 0,
        "extend": True,
        "listing_source": "direct-search",
        "filters": {
            "category": {"id": CATEGORY_VENTE},
            "location": {
                "area": {"lat": CENTER_LAT, "lng": CENTER_LON, "radius": int(RADIUS_KM * 1000)},
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

    try:
        result = client.scrape(ScrapeConfig(
            url="https://api.leboncoin.fr/finder/search",
            method="POST",
            data=json.dumps(payload),
            headers=headers,
            asp=True,
            country="fr",
        ))
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

        type_raw = attrs.get("real_estate_type", "")
        type_bien = TYPE_LABELS.get(str(type_raw), str(type_raw).lower()) if type_raw else ""

        return {
            "id":        f"lbc-{ad.get('list_id')}",
            "source":    "Leboncoin",
            "titre":     ad.get("subject", ""),
            "desc":      ad.get("body", ""),
            "prix":      prix,
            "ville":     loc.get("city", ""),
            "surface":   surface,
            "pieces":    pieces,
            "type_bien": type_bien,
            "lat":       loc.get("lat"),
            "lon":       loc.get("lng"),
            "date":      ad.get("first_publication_date", ""),
            "link":      ad.get("url", f"https://www.leboncoin.fr/annonces/{ad.get('list_id')}"),
            "image":     (ad.get("images") or {}).get("thumb_url", ""),
        }
    except Exception as e:
        print(f"[leboncoin] parse erreur: {e}")
        return None
