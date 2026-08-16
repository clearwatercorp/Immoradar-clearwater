"""Extraction générique des annonces via le balisage schema.org (JSON-LD) que
la plupart des sites immo embarquent dans leurs pages pour le référencement.
C'est plus robuste qu'une API privée reverse-engineered : la structure change
rarement, même quand le site est refondu visuellement."""

import json

from bs4 import BeautifulSoup

LISTING_TYPES = {"Product", "Apartment", "House", "SingleFamilyResidence", "RealEstateListing"}
TYPE_BIEN_MAP = {"Apartment": "appartement", "House": "maison", "SingleFamilyResidence": "maison"}


def extract_jsonld_blocks(html):
    soup = BeautifulSoup(html, "html.parser")
    blocks = []
    for tag in soup.find_all("script", type="application/ld+json"):
        if not tag.string:
            continue
        try:
            data = json.loads(tag.string)
        except Exception:
            continue
        items = data if isinstance(data, list) else [data]
        for item in items:
            if isinstance(item, dict) and "@graph" in item:
                blocks.extend(item["@graph"])
            else:
                blocks.append(item)
    return [b for b in blocks if isinstance(b, dict)]


def _first(value):
    if isinstance(value, list):
        return value[0] if value else ""
    return value or ""


def normalize_jsonld_listing(item, source):
    t = item.get("@type", "")
    types = t if isinstance(t, list) else [t]
    if not LISTING_TYPES.intersection(types):
        return None

    offers = item.get("offers", {}) or {}
    if isinstance(offers, list):
        offers = offers[0] if offers else {}
    geo = item.get("geo", {}) or {}
    address = item.get("address", {}) or {}

    try:
        prix = int(float(offers.get("price") or item.get("price") or 0))
    except (TypeError, ValueError):
        prix = 0

    try:
        lat = float(geo.get("latitude")) if geo.get("latitude") is not None else None
    except (TypeError, ValueError):
        lat = None
    try:
        lon = float(geo.get("longitude")) if geo.get("longitude") is not None else None
    except (TypeError, ValueError):
        lon = None

    surface = item.get("floorSize", {})
    if isinstance(surface, dict):
        surface = surface.get("value")
    try:
        surface = int(float(surface))
    except (TypeError, ValueError):
        surface = 0

    pieces = item.get("numberOfRooms")
    try:
        pieces = int(float(pieces)) if pieces is not None else None
    except (TypeError, ValueError):
        pieces = None

    uid = item.get("sku") or item.get("url") or item.get("name") or ""
    if not uid:
        return None

    type_bien = next((TYPE_BIEN_MAP[t] for t in types if t in TYPE_BIEN_MAP), "")
    if not type_bien:
        blob = f"{item.get('name','')} {item.get('description','')}".lower()
        if "maison" in blob:
            type_bien = "maison"
        elif "appartement" in blob:
            type_bien = "appartement"

    return {
        "id":        f"{source.lower().replace(chr(39), '')}-{uid}",
        "source":    source,
        "titre":     item.get("name", ""),
        "desc":      item.get("description", ""),
        "prix":      prix,
        "type_bien": type_bien,
        "ville":   address.get("addressLocality", ""),
        "surface": surface,
        "pieces":  pieces,
        "lat":     lat,
        "lon":     lon,
        "date":    item.get("datePosted", ""),
        "link":    item.get("url", ""),
        "image":   _first(item.get("image")),
    }
