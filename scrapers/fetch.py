"""Couche de transport HTTP unifiée.

Deux modes, choisis automatiquement selon la présence d'une clé Scrapfly :

1. SCRAPFLY_KEY défini → toutes les requêtes passent par l'API Scrapfly
   (api.scrapfly.io) avec `asp=true` : Scrapfly franchit DataDome
   (Leboncoin), Cloudflare (PAP) et PerimeterX (SeLoger) via ses propres IP
   résidentielles. C'est le mode recommandé en hébergement : le palier
   gratuit de Scrapfly (1000 crédits/mois, renouvelés) suffit pour un usage
   « rafraîchir de temps en temps ».

2. Pas de clé → requête directe via la session fournie (requests /
   curl_cffi / cloudscraper). Fonctionne pour Bien'ici partout, et pour les
   4 sources depuis une connexion résidentielle (usage local).

Chaque fonction retourne un objet `Reponse` uniforme (.status_code, .text,
.json()) quel que soit le mode.
"""

import json as _json
from urllib.parse import urlencode

import requests

from config import SCRAPFLY_KEY

SCRAPFLY_ENDPOINT = "https://api.scrapfly.io/scrape"
TIMEOUT = 70  # Scrapfly + anti-bot peut être lent ; large pour éviter les coupures


class Reponse:
    def __init__(self, status_code, text, url=""):
        self.status_code = status_code
        self.text = text or ""
        self.url = url

    def json(self):
        return _json.loads(self.text)


def enabled():
    return bool(SCRAPFLY_KEY)


def _via_scrapfly(url, method, headers, body, render_js, country):
    params = {
        "key": SCRAPFLY_KEY,
        "url": url,
        "asp": "true",           # anti scraping protection : DataDome, Cloudflare…
        "country": country,
        "method": method,
    }
    if render_js:
        params["render_js"] = "true"
    if headers:
        for k, v in headers.items():
            params[f"headers[{k}]"] = v
    if body is not None:
        params["body"] = body

    r = requests.get(SCRAPFLY_ENDPOINT, params=params, timeout=TIMEOUT)
    # Scrapfly répond toujours 200 en enveloppe ; le vrai statut est dans result.
    try:
        data = r.json()
        result = data.get("result", {})
        return Reponse(result.get("status_code", r.status_code), result.get("content", ""), url)
    except Exception:
        return Reponse(r.status_code, r.text, url)


def get(url, headers=None, session=None, render_js=False, country="fr"):
    if enabled():
        return _via_scrapfly(url, "GET", headers, None, render_js, country)
    s = session or requests
    r = s.get(url, headers=headers, timeout=25)
    return Reponse(r.status_code, r.text, getattr(r, "url", url))


def post(url, data=None, json_body=None, headers=None, session=None, render_js=False, country="fr"):
    if json_body is not None:
        body = _json.dumps(json_body)
        headers = dict(headers or {}, **{"Content-Type": "application/json"})
    elif isinstance(data, dict):
        body = urlencode(data)
        headers = dict(headers or {}, **{"Content-Type": "application/x-www-form-urlencoded"})
    else:
        body = data

    if enabled():
        return _via_scrapfly(url, "POST", headers, body, render_js, country)

    s = session or requests
    r = s.post(url, data=body, headers=headers, timeout=25)
    return Reponse(r.status_code, r.text, getattr(r, "url", url))
