"""Scraper Leboncoin — source prioritaire (de loin le plus gros volume
d'annonces, et le seul où les particuliers publient massivement).

Structure calquée sur le module woob (modules/leboncoin) :
  - catégorie "9" = Ventes immobilières, real_estate_type "1"=maison/"2"=appartement
  - la clé d'API est extraite du JSON __NEXT_DATA__ de la page d'accueil
    (runtimeConfig.API.KEY), elle n'est pas constante.
  - le filtre géographique passe par filters.location.city_zipcodes.
  - attributes["real_estate_type"] est déjà un libellé texte.

Leboncoin est protégé par DataDome, qui filtre en grande partie sur
l'empreinte TLS : une session `requests` est repérée dès la poignée de main,
avant même la lecture des en-têtes. D'où la cascade ci-dessous, qui essaie
plusieurs combinaisons et s'arrête à la première qui fonctionne :

  session   : empreinte TLS Chrome (curl_cffi) puis requests classique
  clé d'API : extraite de la page d'accueil, sinon clé publique connue
              (permet de tenter l'API même quand la page HTML est bloquée,
              l'API mobile étant souvent moins filtrée que le site web)
  filtre géo: liste de communes, puis rayon lat/lon

La combinaison retenue est rapportée dans le diagnostic, ce qui permet de
simplifier ensuite en ne gardant que celle qui marche réellement.
"""

import json

from bs4 import BeautifulSoup

from config import PRICE_MAX_HARD_CAP, CENTER_LAT, CENTER_LON, RADIUS_KM
from zones import COMMUNES
from .http import get_session, get_impersonate_session, impersonate_disponible, TIMEOUT
from . import diag

SOURCE = "Leboncoin"

CATEGORY_VENTE = "9"
REAL_ESTATE_TYPES = ["1", "2"]  # maison, appartement
HOME_URL = "https://www.leboncoin.fr/annonces/offres"
API_URL = "https://api.leboncoin.fr/finder/search"

# Clé publique historiquement utilisée par le site. Sert uniquement de repli
# quand la page d'accueil est inaccessible : si elle est périmée, l'API
# répondra 401 et la cascade passera à la combinaison suivante.
CLE_REPLI = "ba0c2dad52b3ec"

_cache = {"cle": None, "origine": None}


# ─── Clé d'API ────────────────────────────────────────────────────────────
def _extraire_cle(html):
    tag = BeautifulSoup(html, "html.parser").find("script", id="__NEXT_DATA__")
    if not tag or not tag.string:
        return None
    return json.loads(tag.string).get("runtimeConfig", {}).get("API", {}).get("KEY")


def _obtenir_cle(session, trace):
    """Clé fraîche depuis la page d'accueil, sinon clé de repli."""
    if _cache["cle"]:
        return _cache["cle"], _cache["origine"]
    try:
        r = session.get(HOME_URL, timeout=TIMEOUT)
        if r.status_code == 200:
            cle = _extraire_cle(r.text)
            if cle:
                _cache.update(cle=cle, origine="page d'accueil")
                return cle, "page d'accueil"
            trace.append("page d'accueil 200 mais __NEXT_DATA__ inexploitable")
        else:
            trace.append(f"page d'accueil HTTP {r.status_code}")
    except Exception as e:
        trace.append(f"page d'accueil injoignable ({type(e).__name__})")
    return CLE_REPLI, "repli"


# ─── Filtres de recherche ─────────────────────────────────────────────────
def _location_communes():
    return {
        "city_zipcodes": [
            {"city": c["nom"], "zipcode": c["cp"], "label": f"{c['nom']} {c['cp']}"} for c in COMMUNES
        ]
    }


def _location_rayon():
    return {"area": {"lat": CENTER_LAT, "lng": CENTER_LON, "radius": int(RADIUS_KM * 1000)}}


def _payload(location):
    return {
        "limit": 35,
        "limit_alu": 3,
        "sort_by": "time",
        "sort_order": "desc",
        "offset": 0,
        "extend": True,
        "listing_source": "direct-search",
        "filters": {
            "category": {"id": CATEGORY_VENTE},
            "location": location,
            "enums": {"ad_type": ["offer"], "real_estate_type": REAL_ESTATE_TYPES},
            "ranges": {"price": {"max": PRICE_MAX_HARD_CAP}},
        },
    }


def _tenter(session, cle, location):
    """Un essai de recherche. Retourne (annonces_brutes, note)."""
    try:
        r = session.post(
            API_URL,
            data=json.dumps(_payload(location)),
            headers={
                "api_key": cle,
                "content-type": "application/json",
                "accept": "*/*",
                "origin": "https://www.leboncoin.fr",
                "referer": "https://www.leboncoin.fr/recherche",
            },
            timeout=TIMEOUT,
        )
    except Exception as e:
        return None, f"injoignable ({type(e).__name__})"

    if r.status_code != 200:
        return None, f"HTTP {r.status_code}"
    try:
        ads = r.json().get("ads", [])
    except Exception:
        return None, "réponse illisible (non JSON)"
    if not ads:
        return None, "HTTP 200 mais 0 annonce"
    return ads, f"{len(ads)} annonces"


def _sessions():
    sessions = []
    if impersonate_disponible():
        sessions.append(("empreinte Chrome", get_impersonate_session()))
    sessions.append(("requests", get_session()))
    return sessions


def search():
    diag.clear(SOURCE)
    trace = []

    for nom_session, session in _sessions():
        cle, origine = _obtenir_cle(session, trace)

        for nom_filtre, location in (("communes", _location_communes()), ("rayon", _location_rayon())):
            ads, note = _tenter(session, cle, location)
            etiquette = f"{nom_session}/clé {origine}/{nom_filtre}"
            print(f"[leboncoin] {etiquette} → {note}")
            trace.append(f"{etiquette} : {note}")

            if ads:
                diag.set_status(SOURCE, f"OK via {etiquette}")
                return [parsed for a in ads if (parsed := parse_ad(a))]

            # Clé refusée : elle est peut-être périmée, on la réinitialise
            # pour que la session suivante en redemande une fraîche.
            if note.startswith("HTTP 401") or note.startswith("HTTP 403"):
                _cache.update(cle=None, origine=None)
                break

    resume = " | ".join(trace[-4:]) or "aucune tentative aboutie"
    bloque = any(("HTTP 40" in t) or ("HTTP 429" in t) or ("injoignable" in t) for t in trace)
    diag.set_status(SOURCE, resume, bloque=bloque)
    return []


# ─── Normalisation ────────────────────────────────────────────────────────
def parse_ad(ad):
    try:
        prix_list = ad.get("price") or [0]
        prix = prix_list[0] if prix_list else 0
        loc = ad.get("location", {}) or {}
        attrs = {a["key"]: a.get("value_label", a.get("value", "")) for a in ad.get("attributes", [])}

        try:
            surface = int(float(attrs.get("square", 0)))
        except (TypeError, ValueError):
            surface = 0

        try:
            pieces = int(attrs.get("rooms")) if attrs.get("rooms") else None
        except (TypeError, ValueError):
            pieces = None

        dpe_raw = (attrs.get("energy_rate") or "").strip()
        dpe = dpe_raw[0].upper() if dpe_raw and dpe_raw[0].isalpha() else None

        return {
            "id":        f"lbc-{ad.get('list_id')}",
            "source":    SOURCE,
            "titre":     ad.get("subject", ""),
            "desc":      ad.get("body", ""),
            "prix":      prix,
            "ville":     loc.get("city_label") or loc.get("city", ""),
            "cp":        loc.get("zipcode", ""),
            "surface":   surface,
            "pieces":    pieces,
            "type_bien": (attrs.get("real_estate_type") or "").lower(),
            "dpe":       dpe,
            "lat":       loc.get("lat"),
            "lon":       loc.get("lng"),
            "date":      ad.get("first_publication_date", ""),
            "link":      ad.get("url", f"https://www.leboncoin.fr/ventes_immobilieres/{ad.get('list_id')}.htm"),
            "image":     (ad.get("images") or {}).get("thumb_url", ""),
        }
    except Exception as e:
        print(f"[leboncoin] parse erreur: {e}")
        return None
