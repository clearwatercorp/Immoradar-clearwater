import math

from config import CENTER_LAT, CENTER_LON, RADIUS_KM, PRICE_MIN, PRICE_MAX_HARD_CAP
from zones import match_commune


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


def resolve_distance(ad):
    """Distance au centre de la zone. Précise si l'annonce a ses propres
    lat/lon (Leboncoin), sinon approximée via le centre de la commune
    reconnue (PAP/SeLoger/Bien'ici ne renvoient pas de coordonnées) —
    fiable car la recherche elle-même est déjà restreinte aux communes de
    la zone (cf. zones.py), cette distance n'est qu'indicative."""
    dist = distance_from_center(ad.get("lat"), ad.get("lon"))
    if dist is not None:
        return dist, True

    commune = match_commune(ad.get("ville", ""), ad.get("cp", ""))
    if commune:
        return haversine_km(CENTER_LAT, CENTER_LON, commune["lat"], commune["lon"]), False

    return None, False


def filter_reason(ad):
    """Retourne None si l'annonce passe (et l'annote), sinon un code de rejet :
    'sans_coords' / 'hors_zone' / 'prix' / 'sans_surface'. Sert au diagnostic."""
    dist, precise = resolve_distance(ad)
    if dist is None:
        return "sans_coords"
    if dist > RADIUS_KM:
        return "hors_zone"
    prix = ad.get("prix") or 0
    if prix <= PRICE_MIN or prix > PRICE_MAX_HARD_CAP:
        return "prix"
    surface = ad.get("surface") or 0
    if surface <= 0:
        return "sans_surface"
    ad["distance_km"] = round(dist, 1)
    ad["distance_precise"] = precise
    return None


def passes_filters(ad):
    """Filtre une annonce de vente normalisée : dans la zone (précisément
    ou via la commune reconnue), prix et surface exploitables."""
    return filter_reason(ad) is None


def annotate_import(ad):
    """Filtrage SOUPLE pour l'import manuel via le bookmarklet : c'est
    l'utilisateur qui a défini la zone (et le budget) dans sa recherche
    Leboncoin, donc le serveur ne re-filtre PAS par distance ni par prix. Il
    garde tout bien exploitable (prix et surface renseignés) et calcule la
    distance seulement pour l'affichage. Retourne None si gardé (annoté),
    sinon un motif : 'sans_prix' / 'sans_surface'."""
    prix = ad.get("prix") or 0
    if prix <= 0:
        return "sans_prix"
    # On ne rejette PAS sur l'absence de surface : certains biens (résidences
    # gérées / LMNP) n'ont pas de m² dans le titre, or on veut quand même les
    # voir (marqués bail commercial). Le filtre « surface min » de l'app permet
    # de les masquer au besoin.
    dist, precise = resolve_distance(ad)
    if dist is not None:
        ad["distance_km"] = round(dist, 1)
        ad["distance_precise"] = precise
    return None
