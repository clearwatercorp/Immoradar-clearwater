"""Sessions HTTP partagées par les scrapers.

Plus de dépendance à un service payant : on utilise `requests` pour les
sites qui n'ont pas de protection bloquante (Leboncoin, Bien'ici, SeLoger)
et `cloudscraper` pour PAP, qui est derrière Cloudflare — c'est exactement
ce que fait le module woob (CloudScraperMixin sur PAP uniquement).
"""

import requests

BROWSER_HEADERS = {
    "user-agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "accept-language": "fr-FR,fr;q=0.9,en;q=0.8",
    "cache-control": "no-cache",
    "pragma": "no-cache",
    "upgrade-insecure-requests": "1",
}

TIMEOUT = 25

_sessions = {}


def get_session():
    """Session requests classique, réutilisée entre les appels (garde les
    cookies, ce qui aide sur les sites qui posent un cookie de session)."""
    if "plain" not in _sessions:
        s = requests.Session()
        s.headers.update(BROWSER_HEADERS)
        _sessions["plain"] = s
    return _sessions["plain"]


def get_cloudscraper_session():
    """Session cloudscraper (résout le challenge JS Cloudflare). Repli sur
    une session classique si cloudscraper n'est pas installé."""
    if "cloudscraper" not in _sessions:
        try:
            import cloudscraper
            s = cloudscraper.create_scraper(browser={"browser": "chrome", "platform": "windows", "mobile": False})
            s.headers.update({"accept-language": BROWSER_HEADERS["accept-language"]})
        except Exception as e:
            print(f"[http] cloudscraper indisponible ({e}), repli sur requests")
            s = get_session()
        _sessions["cloudscraper"] = s
    return _sessions["cloudscraper"]
