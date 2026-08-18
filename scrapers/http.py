"""Sessions HTTP partagées par les scrapers.

Plus de dépendance à un service payant : on utilise `requests` pour les
sites qui n'ont pas de protection bloquante (Leboncoin, Bien'ici, SeLoger)
et `cloudscraper` pour PAP, qui est derrière Cloudflare — c'est exactement
ce que fait le module woob (CloudScraperMixin sur PAP uniquement).
"""

import requests

from config import PROXY_URL

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


def proxies_dict():
    """Dict proxies (format requests/curl_cffi) ou None si aucun proxy."""
    return {"http": PROXY_URL, "https": PROXY_URL} if PROXY_URL else None


def proxy_actif():
    return bool(PROXY_URL)


def get_session():
    """Session requests classique, réutilisée entre les appels (garde les
    cookies, ce qui aide sur les sites qui posent un cookie de session)."""
    if "plain" not in _sessions:
        s = requests.Session()
        s.headers.update(BROWSER_HEADERS)
        if PROXY_URL:
            s.proxies = proxies_dict()
        _sessions["plain"] = s
    return _sessions["plain"]


def get_impersonate_session():
    """Session curl_cffi imitant l'empreinte TLS/HTTP2 réelle de Chrome.

    Indispensable face à DataDome (Leboncoin) : ces protections identifient
    `requests` dès la poignée de main TLS, avant même de regarder les
    en-têtes HTTP — un User-Agent de navigateur ne suffit donc pas.
    Repli sur une session classique si curl_cffi n'est pas installé.
    """
    if "impersonate" not in _sessions:
        try:
            from curl_cffi import requests as cffi_requests
            s = cffi_requests.Session(impersonate="chrome")
            s.headers.update({"accept-language": BROWSER_HEADERS["accept-language"]})
            if PROXY_URL:
                s.proxies = proxies_dict()
            _sessions["impersonate"] = s
        except Exception as e:
            print(f"[http] curl_cffi indisponible ({e}), repli sur requests")
            _sessions["impersonate"] = get_session()
    return _sessions["impersonate"]


def impersonate_disponible():
    try:
        import curl_cffi  # noqa: F401
        return True
    except Exception:
        return False


def get_cloudscraper_session():
    """Session cloudscraper (résout le challenge JS Cloudflare). Repli sur
    une session classique si cloudscraper n'est pas installé."""
    if "cloudscraper" not in _sessions:
        try:
            import cloudscraper
            s = cloudscraper.create_scraper(browser={"browser": "chrome", "platform": "windows", "mobile": False})
            s.headers.update({"accept-language": BROWSER_HEADERS["accept-language"]})
            if PROXY_URL:
                s.proxies = proxies_dict()
        except Exception as e:
            print(f"[http] cloudscraper indisponible ({e}), repli sur requests")
            s = get_session()
        _sessions["cloudscraper"] = s
    return _sessions["cloudscraper"]
