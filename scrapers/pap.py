"""Scraper PAP.fr (Particulier à Particulier) — annonces de particuliers,
donc peu recroisées avec Leboncoin. Anti-bot léger.

⚠️ Endpoint reverse-engineered et NON testé en conditions réelles (le
bac à sable de dev n'a pas accès réseau vers pap.fr). Si `search()` ne
retourne rien alors que Scrapfly répond HTTP 200, ouvrir la page dans un
navigateur (F12 > Network) pour vérifier l'URL de recherche réelle et
adapter `SEARCH_URL` / `parse_listing_page` en conséquence.
"""

from scrapfly import ScrapeConfig

from config import PRICE_MAX, SURFACE_MIN, ROOMS_MIN
from .jsonld import extract_jsonld_blocks, normalize_jsonld_listing

SEARCH_URL = (
    "https://www.pap.fr/annonce/locations-villeneuve-loubet-06270"
    f"?surface_min={SURFACE_MIN}&prix_max={PRICE_MAX}&nb_pieces_min={ROOMS_MIN}"
)


def search(client):
    if not client:
        return []
    try:
        result = client.scrape(ScrapeConfig(url=SEARCH_URL, asp=True, country="fr"))
        print(f"[pap] HTTP {result.upstream_status_code}")
        if result.upstream_status_code != 200:
            return []
        return parse_listing_page(result.content)
    except Exception as e:
        print(f"[pap] erreur: {e}")
        return []


def parse_listing_page(html):
    results = []
    for item in extract_jsonld_blocks(html):
        parsed = normalize_jsonld_listing(item, "PAP")
        if parsed:
            results.append(parsed)
    if not results:
        print("[pap] aucune annonce reconnue sur la page — structure à vérifier / scraper à mettre à jour")
    return results
