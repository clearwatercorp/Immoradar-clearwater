import math
from config import CENTER_LAT, CENTER_LON, RADIUS_KM, PRICE_MIN, PRICE_MAX_HARD_CAP


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


def passes_filters(ad):
    """Filtre une annonce de vente normalisée : dans la zone, prix et
    surface exploitables. Pas de filtre sur le type de bien ou la surface
    minimale ici — les deux stratégies (location saisonnière / marchand de
    biens) évaluent chaque bien et se chargent elles-mêmes de la pertinence
    (studio/T2 vs maison de ville, etc.)."""
    dist = distance_from_center(ad.get("lat"), ad.get("lon"))
    if dist is None or dist > RADIUS_KM:
        return False
    prix = ad.get("prix") or 0
    if prix <= PRICE_MIN or prix > PRICE_MAX_HARD_CAP:
        return False
    surface = ad.get("surface") or 0
    if surface <= 0:
        return False
    ad["distance_km"] = round(dist, 1)
    return True
