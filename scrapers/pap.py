"""Scraper PAP.fr — calqué sur le module woob (modules/pap) :
  - PAP est derrière Cloudflare : woob utilise `CloudScraperMixin`, donc on
    passe par la lib `cloudscraper` (gratuite) plutôt qu'un service payant.
  - la recherche est un POST form-encoded vers /recherche, avec des
    identifiants de commune internes résolus via /json/ac-geo?q=<nom>.
  - les résultats sont du HTML server-rendu (pas de JSON-LD) : parsing via
    sélecteurs CSS (#pages-list .search-list-item-alt).
"""

import json
import re
from urllib.parse import quote, urlencode

from bs4 import BeautifulSoup

from config import PRICE_MAX_HARD_CAP
from zones import COMMUNES
from .http import get_cloudscraper_session
from . import diag, fetch

SOURCE = "PAP"

AC_GEO_URL = "https://www.pap.fr/json/ac-geo?q={q}"
SEARCH_URL = "https://www.pap.fr/recherche"

_geo_ids_cache = {"ids": None}

# Chaque résolution de commune = 1 requête Scrapfly (l'autocomplete de PAP est
# derrière Cloudflare). Pour économiser les crédits, on ne résout que les
# communes les plus centrales de la zone ; le filtre distance côté serveur
# écarte de toute façon ce qui dépasse le rayon. Ces identifiants étant
# stables, ils sont ensuite mis en cache pour toute la durée de vie du serveur.
COMMUNES_PAP = [c for c in COMMUNES if c["nom"] in (
    "Villeneuve-Loubet", "Antibes", "Cagnes-sur-Mer", "Biot",
)] or COMMUNES


def _resolve_geo_ids(force=False):
    if _geo_ids_cache["ids"] is not None and not force:
        return _geo_ids_cache["ids"]

    session = get_cloudscraper_session()
    ids = []
    derniere_erreur = {"msg": None, "bloque": False}
    for commune in COMMUNES_PAP:
        try:
            r = fetch.get(AC_GEO_URL.format(q=quote(commune["nom"])), session=session)
            if r.status_code != 200:
                derniere_erreur["msg"] = f"autocomplete HTTP {r.status_code}"
                derniere_erreur["bloque"] = r.status_code in (403, 429, 503)
                continue
            data = r.json()
            items = data if isinstance(data, list) else data.get("results", [])
            if items and items[0].get("id"):
                ids.append(str(items[0]["id"]))
        except Exception as e:
            print(f"[pap] erreur résolution commune {commune['nom']}: {e}")
            derniere_erreur["msg"] = f"connexion impossible ({type(e).__name__})"
            derniere_erreur["bloque"] = True

    if ids:
        _geo_ids_cache["ids"] = ids
    elif derniere_erreur["msg"]:
        diag.set_status(SOURCE, f"Communes non résolues : {derniere_erreur['msg']}", bloque=derniere_erreur["bloque"])
    else:
        diag.set_status(SOURCE, "Communes non résolues — l'autocomplete /json/ac-geo ne renvoie plus le format attendu")
    return ids


def search():
    diag.clear(SOURCE)
    geo_ids = _resolve_geo_ids()
    if not geo_ids:
        print("[pap] aucune commune résolue via ac-geo — recherche annulée")
        return []

    data = {
        "geo_objets_ids": ",".join(geo_ids),
        "surface[min]": "",
        "surface[max]": "",
        "prix[min]": "",
        "prix[max]": str(PRICE_MAX_HARD_CAP),
        "produit": "vente",
        "nb_resultats_par_page": 40,
        "action": "submit",
        "nb_chambres[min]": "",
        "surface_terrain[min]": "",
        "surface_terrain[max]": "",
        "transport_objets_ids": "",
        "reference_courte": "",
        "typesbien[]": ["maison", "appartement"],
    }

    try:
        r = fetch.post(
            SEARCH_URL,
            data=urlencode(data, doseq=True),
            headers={"Content-Type": "application/x-www-form-urlencoded;charset=UTF-8"},
            session=get_cloudscraper_session(),
        )
        print(f"[pap] HTTP {r.status_code}")
        if r.status_code != 200:
            diag.set_status(SOURCE, f"Recherche HTTP {r.status_code} — Cloudflare non franchi", bloque=r.status_code in (403, 429, 503))
            return []
        return parse_listing_page(r.text)
    except Exception as e:
        print(f"[pap] erreur: {e}")
        diag.set_status(SOURCE, f"Erreur de recherche : {type(e).__name__}", bloque=True)
        return []


def parse_listing_page(html):
    soup = BeautifulSoup(html, "html.parser")
    container = soup.find("div", id="pages-list")
    if not container:
        print("[pap] #pages-list introuvable — structure de page à vérifier")
        diag.set_status(SOURCE, "Page reçue mais conteneur #pages-list absent — structure du site changée, ou page anti-robot")
        return []

    results = [r for it in container.select("div.search-list-item-alt") if (r := _parse_item(it))]
    if not results:
        print("[pap] page trouvée mais aucune annonce extraite — sélecteurs à vérifier")
        diag.set_status(SOURCE, "Conteneur trouvé mais aucune annonce extraite — sélecteurs CSS à mettre à jour")
    return results


def _clean_int(text):
    digits = re.sub(r"[^\d]", "", text or "")
    return int(digits) if digits else 0


def _parse_item(item):
    link_tag = item.select_one("a.item-title")
    if not link_tag or not link_tag.get("href"):
        return None
    href = link_tag["href"]
    m = re.search(r"/annonces/(.+)", href)
    if not m:
        return None
    ann_id = m.group(1)

    price_tag = link_tag.select_one("span.item-price")
    prix = _clean_int(price_tag.get_text(strip=True)) if price_tag else 0

    tags = link_tag.select("ul.item-tags li")
    surface = None
    pieces = None
    for tag in tags:
        txt = tag.get_text(" ", strip=True).lower()
        num_m = re.search(r"(\d+[.,]?\d*)", txt)
        if not num_m:
            continue
        val = num_m.group(1).replace(",", ".")
        if "pièce" in txt or "piece" in txt:
            pieces = int(float(val))
        elif "m²" in txt or "m2" in txt:
            surface = int(float(val))

    # Le titre contient le prix et les tags (imbriqués dans le même lien) :
    # on les retire pour obtenir un titre lisible.
    title = link_tag.get_text(" ", strip=True)
    for extra in ([price_tag.get_text(strip=True)] if price_tag else []) + [t.get_text(strip=True) for t in tags]:
        title = title.replace(extra, "")
    title = re.sub(r"\s+", " ", title).strip()

    desc_tag = item.select_one("p.item-description")
    desc = desc_tag.get_text(" ", strip=True) if desc_tag else ""
    ville = desc.split(".")[0].strip() if desc else ""

    href_low = href.lower()
    type_bien = "maison" if "maison" in href_low else ("appartement" if "appartement" in href_low else "")

    img_tag = item.select_one("img")
    image = ""
    if img_tag and img_tag.get("src") and "nophoto" not in img_tag["src"] and "miniature-video" not in img_tag["src"]:
        image = img_tag["src"]

    return {
        "id":        f"pap-{ann_id}",
        "source":    "PAP",
        "titre":     title,
        "desc":      desc,
        "prix":      prix,
        "ville":     ville,
        "cp":        "",
        "surface":   surface or 0,
        "pieces":    pieces,
        "type_bien": type_bien,
        "dpe":       None,
        "lat":       None,
        "lon":       None,
        "date":      "",
        "link":      href if href.startswith("http") else f"https://www.pap.fr{href}",
        "image":     image,
    }
