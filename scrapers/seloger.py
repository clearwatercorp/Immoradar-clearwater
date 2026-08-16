"""Scraper SeLoger — essentiellement des annonces d'agences (souvent aussi
présentes sur Leboncoin/Bien'ici en repost), mais utile en complément.

⚠️ SeLoger a la protection anti-bot la plus poussée des 4 sources (Akamai) et
son front est une SPA : c'est la source la plus susceptible de nécessiter un
ajustement une fois lancée en conditions réelles (le bac à sable de dev n'a
pas accès réseau vers seloger.com pour vérifier). Si `search()` ne retourne
rien alors que Scrapfly répond HTTP 200, inspecter la page rendue (F12 >
Network / Elements) et adapter `SEARCH_URL` / `parse_listing_page`.
"""

from scrapfly import ScrapeConfig

from config import CENTER_LAT, CENTER_LON, RADIUS_KM, PRICE_MAX_HARD_CAP
from .jsonld import extract_jsonld_blocks, normalize_jsonld_listing

# projects=1 = vente (achat) sur SeLoger, projects=2 = location — à vérifier
# en conditions réelles, cf. avertissement en tête de fichier.
SEARCH_URL = (
    "https://www.seloger.com/list.htm?types=1,2&projects=1"
    f"&places=[{{lat:{CENTER_LAT},lng:{CENTER_LON},radius:{int(RADIUS_KM * 1000)}}}]"
    f"&price=NaN/{PRICE_MAX_HARD_CAP}&enterprise=0&qsVersion=1.0"
)


def search(client):
    if not client:
        return []
    try:
        result = client.scrape(ScrapeConfig(url=SEARCH_URL, asp=True, country="fr", render_js=True))
        print(f"[seloger] HTTP {result.upstream_status_code}")
        if result.upstream_status_code != 200:
            return []
        return parse_listing_page(result.content)
    except Exception as e:
        print(f"[seloger] erreur: {e}")
        return []


def parse_listing_page(html):
    results = []
    for item in extract_jsonld_blocks(html):
        parsed = normalize_jsonld_listing(item, "SeLoger")
        if parsed:
            results.append(parsed)
    if not results:
        print("[seloger] aucune annonce reconnue sur la page — structure à vérifier / scraper à mettre à jour")
    return results
