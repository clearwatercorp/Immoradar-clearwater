"""Scraper SeLoger — entièrement réécrit d'après le module woob
(modules/seloger), qui révèle que :
  - la page de résultats n'a PAS de __NEXT_DATA__ ni de JSON-LD (mon
    hypothèse initiale était fausse) : les annonces sont dans un
    `window["initialData"] = JSON.parse("...")` embarqué dans un <script>,
    sous forme de chaîne JS doublement échappée.
  - le filtre géographique se fait par codes INSEE (`places=[{"inseeCodes":
    [...]}]`), pas par centre/rayon lat-lon.
  - projects=2 correspond à la vente (achat), projects=1 à la location —
    j'avais les deux inversés dans la première version.
  - SeLoger a la protection anti-bot la plus poussée des 4 sources
    (Akamai/Reblaze, avec une page de captcha dédiée) : c'est toujours la
    source la plus susceptible de nécessiter un ajustement en conditions
    réelles.
"""

import codecs
import json
import re

from scrapfly import ScrapeConfig

from config import PRICE_MAX_HARD_CAP
from zones import COMMUNES

BASE_URL = "https://www.seloger.com"
INSEE_CODES = [c["insee"].lstrip("0") or "0" for c in COMMUNES]  # SeLoger attend des codes non préfixés de zéro

PROJECT_VENTE = 2
TYPES_APART_MAISON = "1,2"  # 1=appartement, 2=maison


def _build_url():
    places = "[{\"inseeCodes\": [" + ",".join(INSEE_CODES) + "]}]"
    query = (
        f"projects={PROJECT_VENTE}&natures=1,2,4&places={places}"
        f"&types={TYPES_APART_MAISON}&price=0/{PRICE_MAX_HARD_CAP}&surface=0/Nan"
        f"&enterprise=0&qsVersion=1.0"
    )
    return f"{BASE_URL}/list.html?{query}&LISTING-LISTpg=1"


def search(client):
    if not client:
        return []
    try:
        result = client.scrape(ScrapeConfig(url=_build_url(), asp=True, country="fr", render_js=True))
        print(f"[seloger] HTTP {result.upstream_status_code}")
        if result.upstream_status_code != 200:
            return []
        return parse_listing_page(result.content)
    except Exception as e:
        print(f"[seloger] erreur: {e}")
        return []


def _extract_initial_data(html):
    m = re.search(r'window\["initialData"\] = JSON\.parse\("(.*?)"\);window\["tags"\]', html, re.S)
    if not m:
        return None
    raw = m.group(1)
    try:
        decoded = codecs.unicode_escape_decode(raw)[0]
        decoded = decoded.encode("utf-8", "surrogatepass").decode("utf-8")
        return json.loads(decoded)
    except Exception as e:
        print(f"[seloger] erreur décodage initialData: {e}")
        return None


def parse_listing_page(html):
    data = _extract_initial_data(html)
    if not data:
        print("[seloger] window[\"initialData\"] introuvable ou illisible — structure de page à vérifier")
        return []

    cards = (data.get("cards") or {}).get("list") or []
    results = [r for c in cards if (r := _parse_card(c))]
    if not results:
        print("[seloger] initialData trouvé mais aucune annonce extraite — structure à vérifier")
    return results


TYPE_BIEN_MAP = {"1": "appartement", "2": "maison"}


def _parse_card(card):
    try:
        url = card.get("classifiedURL", "")
        if not url or not url.startswith(BASE_URL):
            return None
        ann_id = card.get("id")
        if not ann_id:
            return None

        pricing = card.get("pricing") or {}
        prix = pricing.get("price") or 0
        try:
            prix = int(float(prix))
        except (TypeError, ValueError):
            prix = 0

        surface = card.get("surface") or 0
        try:
            surface = int(float(surface))
        except (TypeError, ValueError):
            surface = 0

        photos = card.get("photos") or []
        image = photos[0] if photos and isinstance(photos[0], str) else ""

        cp = str(card.get("zipCode") or "")

        return {
            "id":        f"seloger-{ann_id}",
            "source":    "SeLoger",
            "titre":     f"{card.get('estateType', 'Bien')} - {card.get('cityLabel', '')}".strip(" -"),
            "desc":      card.get("description", ""),
            "prix":      prix,
            "ville":     card.get("cityLabel", ""),
            "cp":        cp,
            "surface":   surface,
            "pieces":    None,
            "type_bien": TYPE_BIEN_MAP.get(str(card.get("estateTypeId", "")), ""),
            "dpe":       None,
            "lat":       None,
            "lon":       None,
            "date":      "",
            "link":      url,
            "image":     image,
        }
    except Exception as e:
        print(f"[seloger] parse erreur: {e}")
        return None
