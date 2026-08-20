"""Scraper Leboncoin — source prioritaire (de loin le plus gros volume).

Leboncoin est protégé par DataDome, qui filtre surtout sur l'empreinte TLS
et sur le fait de se présenter comme un navigateur web. La technique qui
passe gratuitement, documentée par la communauté et implémentée par la
bibliothèque open-source `lbc` (MIT, github.com/etienne-hd/lbc), est de se
faire passer non pas pour un navigateur mais pour l'**application mobile**
Leboncoin :

  - requêtes via curl_cffi (empreinte TLS/HTTP2 d'un vrai navigateur mobile) ;
  - User-Agent applicatif « LBC;iOS;18.x;iPhone;phone;<uuid>;wifi;101.x » ;
  - initialisation des cookies DataDome par une visite préalable de la home ;
  - sur 403, on ré-initialise entièrement la session (autre appareil, autres
    cookies) et on retente — DataDome est probabiliste, un nouvel essai passe
    souvent.

Cette API mobile (api.leboncoin.fr) est bien moins filtrée que le site web.

On s'appuie sur `lbc` comme moteur principal (maintenu : une mise à jour de
la lib suffit si Leboncoin change), avec repli sur une implémentation
curl_cffi interne si la lib est absente ou échoue.
"""

from urllib.parse import urlparse

from config import PRICE_MAX_HARD_CAP, CENTER_LAT, CENTER_LON, RADIUS_KM, VILLE_CENTRE, PROXY_URL
from .http import proxies_dict
from . import diag, fetch

SOURCE = "Leboncoin"

REAL_ESTATE_TYPES = ("1", "2")  # maison, appartement


def search():
    diag.clear(SOURCE)
    # En hébergement avec Scrapfly : l'API mobile passée par Scrapfly franchit
    # DataDome. C'est le chemin prioritaire dès qu'une clé est configurée.
    if fetch.enabled():
        return _search_via_scrapfly()
    # Sinon (usage local / résidentiel) : la lib lbc suffit.
    ads = _search_via_lbc()
    if ads is not None:
        return ads
    return _search_interne()


def _search_via_scrapfly():
    try:
        r = fetch.post(
            API_URL,
            json_body=_payload(),
            headers={"api_key": _CLE_API_PUBLIQUE},
            country="fr",
        )
        if r.status_code != 200:
            diag.set_status(SOURCE, f"API mobile via Scrapfly : HTTP {r.status_code}", bloque=r.status_code in (401, 403, 429))
            return []
        ads = r.json().get("ads", [])
        print(f"[leboncoin] Scrapfly → {len(ads)} annonces")
        if not ads:
            diag.set_status(SOURCE, "API mobile OK (Scrapfly) mais aucune annonce dans la zone/les critères")
        return [parsed for a in ads if (parsed := _parse_api_ad(a))]
    except Exception as e:
        print(f"[leboncoin] Scrapfly erreur: {e}")
        diag.set_status(SOURCE, f"Erreur via Scrapfly : {type(e).__name__}", bloque=True)
        return []


# Clé publique de l'appli mobile (historiquement stable). Utilisée uniquement
# via Scrapfly, où DataDome est franchi par le service.
_CLE_API_PUBLIQUE = "ba0c2dad52b3ec"


# ─── Moteur principal : bibliothèque lbc ──────────────────────────────────
def _lbc_proxy():
    """Convertit PROXY_URL en objet lbc.Proxy, ou None."""
    if not PROXY_URL:
        return None
    try:
        import lbc
        p = urlparse(PROXY_URL)
        return lbc.Proxy(
            host=p.hostname, port=p.port or 80,
            username=p.username, password=p.password,
            scheme=p.scheme or "http",
        )
    except Exception as e:
        print(f"[leboncoin] PROXY_URL invalide ({e}), ignoré")
        return None


def _search_via_lbc():
    """Retourne la liste d'annonces, ou None si la lib n'est pas utilisable
    (dans ce cas on tente le moteur interne). Une liste vide = la lib a
    répondu mais sans résultat / bloquée : on ne tente pas le repli, il
    utiliserait la même technique."""
    try:
        import lbc
    except Exception as e:
        print(f"[leboncoin] lib lbc indisponible ({e}) — repli interne")
        return None

    try:
        client = lbc.Client(proxy=_lbc_proxy())
        location = lbc.City(lat=CENTER_LAT, lng=CENTER_LON, radius=int(RADIUS_KM * 1000), city=VILLE_CENTRE)
        result = client.search(
            locations=[location],
            category=lbc.Category.IMMOBILIER_VENTES_IMMOBILIERES,
            sort=lbc.Sort.NEWEST,
            limit=35,
            real_estate_type=REAL_ESTATE_TYPES,
            price=(0, PRICE_MAX_HARD_CAP),
        )
        ads = [parsed for a in result.ads if (parsed := _parse_lbc_ad(a))]
        print(f"[leboncoin] lbc → {len(result.ads)} annonces, {len(ads)} exploitables")
        if not ads:
            diag.set_status(SOURCE, "API mobile OK mais aucune annonce dans la zone/les critères")
        return ads
    except Exception as e:
        nom = type(e).__name__
        # DatadomeError = blocage après tous les retries de la lib.
        if "Datadome" in nom:
            print("[leboncoin] lbc bloqué par DataDome après retries")
            diag.set_status(SOURCE, "Bloqué par DataDome (API mobile) malgré plusieurs tentatives", bloque=True)
            return []
        print(f"[leboncoin] lbc erreur {nom}: {e} — repli interne")
        return None


def _lbc_attr(ad, key):
    attr = (ad.attributes or {}).get(key)
    return attr.value_label if attr else None


def _parse_lbc_ad(ad):
    try:
        loc = ad.location

        surface = 0
        try:
            surface = int(float(_lbc_attr(ad, "square") or 0))
        except (TypeError, ValueError):
            pass

        pieces = None
        try:
            rooms = _lbc_attr(ad, "rooms")
            pieces = int(rooms) if rooms else None
        except (TypeError, ValueError):
            pass

        dpe_raw = (_lbc_attr(ad, "energy_rate") or "").strip()
        dpe = dpe_raw[0].upper() if dpe_raw and dpe_raw[0].isalpha() else None

        images = ad.images or []

        return {
            "id":        f"lbc-{ad.id}",
            "source":    SOURCE,
            "titre":     ad.subject or "",
            "desc":      ad.body or "",
            "prix":      int(ad.price or 0),
            "ville":     getattr(loc, "city_label", None) or getattr(loc, "city", "") or "",
            "cp":        getattr(loc, "zipcode", "") or "",
            "surface":   surface,
            "pieces":    pieces,
            "type_bien": (_lbc_attr(ad, "real_estate_type") or "").lower(),
            "dpe":       dpe,
            "lat":       getattr(loc, "lat", None),
            "lon":       getattr(loc, "lng", None),
            "date":      ad.first_publication_date or "",
            "link":      ad.url or f"https://www.leboncoin.fr/ventes_immobilieres/{ad.id}.htm",
            "image":     images[0] if images else "",
        }
    except Exception as e:
        print(f"[leboncoin] parse lbc erreur: {e}")
        return None


# ─── Repli interne : curl_cffi + User-Agent appli mobile ──────────────────
# Reproduit la même technique que lbc, en autonome, pour le cas où la lib
# n'est pas installée sur l'hébergeur.
import json      # noqa: E402
import random    # noqa: E402
import uuid      # noqa: E402

API_URL = "https://api.leboncoin.fr/finder/search"
HOME_URL = "https://www.leboncoin.fr/"


def _user_agent_mobile():
    ios = random.choice([True, True, False])
    if ios:
        ver = random.choice(["18.3", "18.4", "18.5", "18.6", "26.0", "26.1"])
        app = random.choice(["101.44.0", "101.43.1", "101.42.0", "101.45.0"])
        return f"LBC;iOS;{ver};iPhone;phone;{uuid.uuid4()};wifi;{app}"
    ver = random.choice(["12", "13", "14", "15"])
    model = random.choice(["Pixel 7", "Pixel 8", "SM-G991B", "SM-S918B", "Redmi Note 12"])
    app = random.choice(["100.85.2", "100.84.1", "100.83.1"])
    return f"LBC;Android;{ver};{model};phone;{uuid.uuid4().hex[:16]};wifi;{app}"


def _payload():
    return {
        "filters": {
            "category": {"id": "9"},
            "enums": {"ad_type": ["offer"], "real_estate_type": list(REAL_ESTATE_TYPES)},
            "keywords": {"text": None},
            "location": {"locations": [{
                "locationType": "city",
                "city": VILLE_CENTRE,
                "label": f"{VILLE_CENTRE} (toute la ville)",
                "area": {"lat": CENTER_LAT, "lng": CENTER_LON, "radius": int(RADIUS_KM * 1000)},
            }]},
            "ranges": {"price": {"min": 0, "max": PRICE_MAX_HARD_CAP}},
        },
        "limit": 35, "limit_alu": 3, "offset": 0,
        "disable_total": True, "extend": True, "listing_source": "direct-search",
        "sort_by": "time", "sort_order": "desc",
    }


def _nouvelle_session():
    try:
        from curl_cffi import requests as cffi
    except Exception as e:
        print(f"[leboncoin] curl_cffi absent ({e}) — repli impossible")
        return None
    navigateur = random.choice(["safari_ios", "chrome_android", "safari", "firefox"])
    s = cffi.Session(impersonate=navigateur)
    if PROXY_URL:
        s.proxies = proxies_dict()
    s.headers.update({
        "User-Agent": _user_agent_mobile(),
        "Sec-Fetch-Dest": "empty", "Sec-Fetch-Mode": "cors", "Sec-Fetch-Site": "same-site",
    })
    try:
        s.get(HOME_URL, timeout=30)  # amorce les cookies DataDome
    except Exception:
        pass
    return s


def _search_interne(max_essais=4):
    dernier = None
    for essai in range(1, max_essais + 1):
        session = _nouvelle_session()
        if session is None:
            diag.set_status(SOURCE, "Ni la lib lbc ni curl_cffi ne sont installés", bloque=False)
            return []
        try:
            r = session.post(API_URL, json=_payload(), timeout=30)
            if r.status_code == 200:
                ads = r.json().get("ads", [])
                print(f"[leboncoin] repli interne (essai {essai}) → {len(ads)} annonces")
                if not ads:
                    diag.set_status(SOURCE, "API mobile OK mais aucune annonce dans la zone/les critères")
                return [parsed for a in ads if (parsed := _parse_api_ad(a))]
            dernier = f"HTTP {r.status_code}"
            print(f"[leboncoin] repli interne (essai {essai}) → {dernier}, nouvelle session")
        except Exception as e:
            dernier = f"injoignable ({type(e).__name__})"
            print(f"[leboncoin] repli interne (essai {essai}) → {dernier}")

    diag.set_status(SOURCE, f"Bloqué après {max_essais} tentatives (dernier : {dernier})", bloque=True)
    return []


import re as _re


def _to_int(v):
    try:
        return int(float(str(v).replace(",", ".")))
    except (TypeError, ValueError):
        return 0


def _parse_api_ad(ad):
    """Normalise une annonce Leboncoin. Défensif : le format des annonces
    embarquées dans les pages (__NEXT_DATA__) varie et n'a pas toujours le
    même schéma que l'API mobile. On cherche donc chaque donnée à plusieurs
    endroits, avec repli sur une extraction depuis le titre."""
    try:
        # Prix : liste [n] ou nombre, ou champ price_cents.
        prix = 0
        pr = ad.get("price")
        if isinstance(pr, list) and pr:
            prix = _to_int(pr[0])
        elif isinstance(pr, (int, float, str)):
            prix = _to_int(pr)
        if not prix and ad.get("price_cents"):
            prix = _to_int(ad["price_cents"]) // 100

        loc = ad.get("location", {}) or {}

        # Attributs : liste [{key,value,value_label}] → dict par clé (souvent
        # absents dans les pages de liste, d'où les replis ci-dessous).
        attrs = {}
        for a in (ad.get("attributes") or []):
            if isinstance(a, dict) and a.get("key"):
                attrs[a["key"]] = a.get("value_label") or a.get("value") or ""

        titre = ad.get("subject") or ad.get("title") or ""
        desc = ad.get("body") or ad.get("description") or ""
        texte = f"{titre} {desc}"

        # Surface : attribut square/surface, sinon champ direct, sinon titre (« 45 m² »).
        surface = _to_int(attrs.get("square") or attrs.get("surface") or ad.get("square") or ad.get("surface"))
        if not surface:
            m = _re.search(r"(\d{2,4})\s*m(?:²|2|²)", texte, _re.I)
            if m:
                surface = _to_int(m.group(1))

        # Pièces : attribut rooms, sinon titre (« T3 », « 3 pièces »).
        pieces = _to_int(attrs.get("rooms") or ad.get("rooms")) or None
        if not pieces:
            m = _re.search(r"\b[TFtf]\s?([1-9])\b|\b([1-9])\s*pi[eè]ces?\b", texte)
            if m:
                pieces = _to_int(m.group(1) or m.group(2)) or None

        dpe_raw = (attrs.get("energy_rate") or ad.get("energy_rate") or "").strip()
        dpe = dpe_raw[0].upper() if dpe_raw and dpe_raw[0].isalpha() else None

        # Type de bien : attribut, sinon déduit du titre.
        type_bien = (attrs.get("real_estate_type") or "").lower()
        if type_bien in ("1", "maison"):
            type_bien = "maison"
        elif type_bien in ("2", "appartement"):
            type_bien = "appartement"
        elif not type_bien:
            low = texte.lower()
            if "maison" in low or "villa" in low:
                type_bien = "maison"
            elif "appartement" in low or _re.search(r"\b[TFtf]\s?[1-9]\b", texte):
                type_bien = "appartement"

        # Ville / CP : plusieurs schémas possibles.
        ville = (loc.get("city_label") or loc.get("city") or loc.get("city_name")
                 or ad.get("city_label") or ad.get("city") or "")
        cp = str(loc.get("zipcode") or loc.get("zip_code") or ad.get("zipcode") or "")
        lat = loc.get("lat") if loc.get("lat") is not None else ad.get("lat")
        lon = (loc.get("lng") if loc.get("lng") is not None
               else loc.get("lon") if loc.get("lon") is not None else ad.get("lng"))

        images = ad.get("images") or {}
        image = ""
        if isinstance(images, dict):
            image = images.get("thumb_url") or (images.get("urls") or [""])[0] if images.get("urls") else images.get("thumb_url", "")
        elif isinstance(images, list) and images:
            image = images[0] if isinstance(images[0], str) else (images[0].get("url", "") if isinstance(images[0], dict) else "")

        list_id = ad.get("list_id") or ad.get("id")

        return {
            "id":        f"lbc-{list_id}",
            "source":    SOURCE,
            "titre":     titre,
            "desc":      desc,
            "prix":      prix,
            "ville":     ville,
            "cp":        cp,
            "surface":   surface,
            "pieces":    pieces,
            "type_bien": type_bien,
            "dpe":       dpe,
            "lat":       lat,
            "lon":       lon,
            "date":      ad.get("first_publication_date") or ad.get("index_date") or "",
            "link":      ad.get("url") or f"https://www.leboncoin.fr/ventes_immobilieres/{list_id}.htm",
            "image":     image,
        }
    except Exception as e:
        print(f"[leboncoin] parse api erreur: {e}")
        return None
