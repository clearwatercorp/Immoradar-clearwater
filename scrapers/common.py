import math
import re

from config import CENTER_LAT, CENTER_LON, RADIUS_KM, SURFACE_MIN, PRICE_MAX, ROOMS_MIN

STUDIO_RE = re.compile(r"\bstudio\b|\bT1\b|\bF1\b|\b1\s*pi[eè]ce\b", re.IGNORECASE)


def haversine_km(lat1, lon1, lat2, lon2):
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def distance_from_center(lat, lon):
    if lat is None or lon is None:
        return None
    try:
        return haversine_km(CENTER_LAT, CENTER_LON, float(lat), float(lon))
    except (TypeError, ValueError):
        return None


def looks_like_studio(titre="", desc="", pieces=None):
    if pieces:
        return pieces < ROOMS_MIN
    return bool(STUDIO_RE.search(f"{titre or ''} {desc or ''}"))


def passes_filters(ad):
    """Filtre une annonce normalisée selon la zone (rayon) et les critères
    (surface mini, loyer maxi, pas de studio). Annonce sans coordonnées ou
    sans surface connue = rejetée (on préfère rater une annonce plutôt que
    d'en afficher une potentiellement hors zone)."""
    dist = distance_from_center(ad.get("lat"), ad.get("lon"))
    if dist is None or dist > RADIUS_KM:
        return False
    surface = ad.get("surface") or 0
    if surface < SURFACE_MIN:
        return False
    prix = ad.get("prix") or 0
    if prix <= 0 or prix > PRICE_MAX:
        return False
    if looks_like_studio(ad.get("titre", ""), ad.get("desc", ""), ad.get("pieces")):
        return False
    ad["distance_km"] = round(dist, 1)
    return True
