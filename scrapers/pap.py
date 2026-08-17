"""Scraper PAP.fr — entièrement réécrit d'après le module woob
(modules/pap), qui révèle que :
  - PAP n'a PAS de balisage JSON-LD sur ses pages de résultats (mon
    hypothèse initiale était fausse) : c'est du HTML server-rendu classique
    à parser via sélecteurs CSS (#pages-list .search-list-item-alt).
  - La recherche est un POST form-encoded vers /recherche (pas une URL
    slug SEO), avec des identifiants de commune internes à résoudre via
    l'autocomplete /json/ac-geo?q=<nom>.
  - Le site est protégé par Cloudflare (CloudScraperMixin côté woob) —
    Scrapfly (asp=True) est censé gérer ça nativement.
"""

import json
import re
from urllib.parse import quote, urlencode

from bs4 import BeautifulSoup
from scrapfly import ScrapeConfig

from config import PRICE_MAX_HARD_CAP
from zones import COMMUNES

AC_GEO_URL = "https://www.pap.fr/json/ac-geo?q={q}"
SEARCH_URL = "https://www.pap.fr/recherche"

_geo_ids_cache = {"ids": None}


def _resolve_geo_ids(client, force=False):
    if _geo_ids_cache["ids"] is not None and not force:
        return _geo_ids_cache["ids"]

    ids = []
    for commune in COMMUNES:
        try:
            url = AC_GEO_URL.format(q=quote(commune["nom"]))
            result = client.scrape(ScrapeConfig(url=url, asp=True, country="fr"))
            if result.upstream_status_code != 200:
                continue
            data = json.loads(result.content)
            items = data if isinstance(data, list) else data.get("results", [])
            if items and items[0].get("id"):
                ids.append(str(items[0]["id"]))
        except Exception as e:
            print(f"[pap] erreur résolution commune {commune['nom']}: {e}")

    if ids:
        _geo_ids_cache["ids"] = ids
    return ids


def search(client):
    if not client:
        return []

    geo_ids = _resolve_geo_ids(client)
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
    body = urlencode(data, doseq=True)

    try:
        result = client.scrape(ScrapeConfig(
            url=SEARCH_URL,
            method="POST",
            data=body,
            headers={"Content-Type": "application/x-www-form-urlencoded;charset=UTF-8"},
            asp=True,
            country="fr",
        ))
        print(f"[pap] HTTP {result.upstream_status_code}")
        if result.upstream_status_code != 200:
            return []
        return parse_listing_page(result.content)
    except Exception as e:
        print(f"[pap] erreur: {e}")
        return []


def parse_listing_page(html):
    soup = BeautifulSoup(html, "html.parser")
    container = soup.find("div", id="pages-list")
    if not container:
        print("[pap] #pages-list introuvable — structure de page à vérifier")
        return []

    items = container.select("div.search-list-item-alt")
    results = [r for it in items if (r := _parse_item(it))]
    if not results:
        print("[pap] page trouvée mais aucune annonce extraite — sélecteurs à vérifier")
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

    # Le titre inclut le prix et les tags dans le HTML brut (ils sont
    # imbriqués dans le même lien) : on les retire pour un titre lisible.
    title = link_tag.get_text(" ", strip=True)
    for extra in ([price_tag.get_text(strip=True)] if price_tag else []) + [t.get_text(strip=True) for t in tags]:
        title = title.replace(extra, "")
    title = re.sub(r"\s+", " ", title).strip()

    desc_tag = item.select_one("p.item-description")
    desc = desc_tag.get_text(" ", strip=True) if desc_tag else ""
    ville = desc.split(".")[0].strip() if desc else ""

    href_low = href.lower()
    if "maison" in href_low:
        type_bien = "maison"
    elif "appartement" in href_low:
        type_bien = "appartement"
    else:
        type_bien = ""

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
