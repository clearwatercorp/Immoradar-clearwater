"""Scraper SeLoger — calqué sur le module woob (modules/seloger) :
  - les annonces sont dans un `window["initialData"] = JSON.parse("...")`
    embarqué dans un <script> (chaîne JS doublement échappée), pas de
    JSON-LD ni de __NEXT_DATA__ sur la page de liste.
  - filtre géographique par codes INSEE (`places=[{"inseeCodes":[...]}]`).
  - projects=2 = vente, projects=1 = location.

⚠️ C'est la source la plus fragile des quatre : SeLoger est protégé par
Reblaze/PerimeterX et woob lui-même ne contourne pas le captcha (il lève
une erreur "Please resolve the captcha"). Sans service anti-bot payant,
cette source peut échouer — l'échec est détecté et journalisé
explicitement, et les trois autres sources continuent de tourner.
"""

import codecs
import json
import re
from urllib.parse import quote

from config import PRICE_MAX_HARD_CAP
from zones import COMMUNES
from .http import get_session, TIMEOUT
from . import diag

SOURCE = "SeLoger"

BASE_URL = "https://www.seloger.com"
AUTOCOMPLETE_URL = "https://autocomplete.svc.groupe-seloger.com/auto/complete/0/Ville/6?text={q}"

PROJECT_VENTE = 2
TYPES_APART_MAISON = "1,2"  # 1=appartement, 2=maison

_city_ids_cache = {"ids": None}


def _resolve_city_ids(force=False):
    """Résout les identifiants de commune via l'autocomplete de SeLoger
    (champ Params.ci), comme le fait woob — plus fiable que de coder en
    dur des codes INSEE. Repli sur les codes INSEE de zones.py si
    l'autocomplete est inaccessible."""
    if _city_ids_cache["ids"] is not None and not force:
        return _city_ids_cache["ids"]

    session = get_session()
    ids = []
    for commune in COMMUNES:
        try:
            r = session.get(
                AUTOCOMPLETE_URL.format(q=quote(commune["nom"])),
                headers={"accept": "application/json"},
                timeout=TIMEOUT,
            )
            if r.status_code != 200:
                continue
            data = r.json()
            items = data if isinstance(data, list) else (data.get("Items") or data.get("items") or [])
            for item in items:
                ci = (item.get("Params") or item.get("params") or {}).get("ci")
                if ci:
                    ids.append(str(ci))
                    break
        except Exception as e:
            print(f"[seloger] erreur résolution commune {commune['nom']}: {e}")

    if not ids:
        ids = [c["insee"].lstrip("0") or "0" for c in COMMUNES]
        print("[seloger] autocomplete indisponible — repli sur les codes INSEE de zones.py")

    _city_ids_cache["ids"] = ids
    return ids


def _build_url(city_ids):
    places = '[{"inseeCodes": [' + ",".join(city_ids) + "]}]"
    query = (
        f"projects={PROJECT_VENTE}&natures=1,2,4&places={places}"
        f"&types={TYPES_APART_MAISON}&price=0/{PRICE_MAX_HARD_CAP}&surface=0/Nan"
        f"&enterprise=0&qsVersion=1.0"
    )
    return f"{BASE_URL}/list.html?{query}&LISTING-LISTpg=1"


def search():
    diag.clear(SOURCE)
    try:
        r = get_session().get(_build_url(_resolve_city_ids()), timeout=TIMEOUT)
        print(f"[seloger] HTTP {r.status_code}")
        if r.status_code != 200:
            if r.status_code in (403, 429):
                print("[seloger] bloqué par l'anti-bot (captcha probable) — source ignorée pour ce cycle")
                diag.set_status(SOURCE, f"HTTP {r.status_code} — bloqué par l'anti-robot (captcha)", bloque=True)
            else:
                diag.set_status(SOURCE, f"Recherche HTTP {r.status_code}", bloque=False)
            return []
        if "validate.perfdrive" in r.url or "captcha" in r.text[:2000].lower():
            print("[seloger] page de captcha renvoyée — source ignorée pour ce cycle")
            diag.set_status(SOURCE, "Page de captcha renvoyée — bloqué par l'anti-robot", bloque=True)
            return []
        return parse_listing_page(r.text)
    except Exception as e:
        print(f"[seloger] erreur: {e}")
        diag.set_status(SOURCE, f"Erreur de recherche : {type(e).__name__}", bloque=True)
        return []


def _extract_initial_data(html):
    m = re.search(r'window\["initialData"\] = JSON\.parse\("(.*?)"\);window\["tags"\]', html, re.S)
    if not m:
        return None
    try:
        decoded = codecs.unicode_escape_decode(m.group(1))[0]
        decoded = decoded.encode("utf-8", "surrogatepass").decode("utf-8")
        return json.loads(decoded)
    except Exception as e:
        print(f"[seloger] erreur décodage initialData: {e}")
        return None


def parse_listing_page(html):
    data = _extract_initial_data(html)
    if not data:
        print('[seloger] window["initialData"] introuvable ou illisible — structure de page à vérifier')
        diag.set_status(SOURCE, 'Page reçue mais window["initialData"] absent — page anti-robot ou structure changée', bloque=True)
        return []

    cards = (data.get("cards") or {}).get("list") or []
    results = [r for c in cards if (r := _parse_card(c))]
    if not results:
        print("[seloger] initialData trouvé mais aucune annonce extraite — structure à vérifier")
        diag.set_status(SOURCE, f"Données trouvées ({len(cards)} fiches) mais aucune exploitable — structure à mettre à jour")
    return results


TYPE_BIEN_MAP = {"1": "appartement", "2": "maison"}


def _parse_card(card):
    try:
        url = card.get("classifiedURL", "")
        ann_id = card.get("id")
        if not url or not url.startswith(BASE_URL) or not ann_id:
            return None

        try:
            prix = int(float((card.get("pricing") or {}).get("price") or 0))
        except (TypeError, ValueError):
            prix = 0

        try:
            surface = int(float(card.get("surface") or 0))
        except (TypeError, ValueError):
            surface = 0

        photos = card.get("photos") or []

        return {
            "id":        f"seloger-{ann_id}",
            "source":    "SeLoger",
            "titre":     f"{card.get('estateType', 'Bien')} - {card.get('cityLabel', '')}".strip(" -"),
            "desc":      card.get("description", ""),
            "prix":      prix,
            "ville":     card.get("cityLabel", ""),
            "cp":        str(card.get("zipCode") or ""),
            "surface":   surface,
            "pieces":    None,
            "type_bien": TYPE_BIEN_MAP.get(str(card.get("estateTypeId", "")), ""),
            "dpe":       None,
            "lat":       None,
            "lon":       None,
            "date":      "",
            "link":      url,
            "image":     photos[0] if photos and isinstance(photos[0], str) else "",
        }
    except Exception as e:
        print(f"[seloger] parse erreur: {e}")
        return None
