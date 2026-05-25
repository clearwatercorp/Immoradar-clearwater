import os
import json
import time
import threading
from flask import Flask, jsonify, send_file
from curl_cffi import requests as curl_requests

app = Flask(__name__)

PORT       = int(os.environ.get("PORT", 3000))
CACHE_TTL  = 15 * 60
IDF_REGION = "12"
IMMO_CAT   = "9"
PRIX_MIN   = 400000
PRIX_MAX   = 800000

KEYWORDS = [
    "immeuble",
    "immeuble de rapport",
    "immeuble locatif",
    "immeuble entier",
    "maison divisée",
    "bien de rapport",
    "plurifamilial",
    "maison de ville",
]

_cache = {"data": [], "ts": 0}
_lock  = threading.Lock()

def make_session():
    return curl_requests.Session(impersonate="chrome120")

SESSION = make_session()

def search_lbc(keyword, offset=0, limit=35):
    headers = {
        "accept": "*/*",
        "accept-language": "fr-FR,fr;q=0.9",
        "api_key": "ba0c2dad52b3ec",
        "content-type": "application/json",
        "origin": "https://www.leboncoin.fr",
        "referer": "https://www.leboncoin.fr/recherche",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    }
    payload = {
        "limit": limit,
        "limit_alu": 3,
        "sort_by": "time",
        "sort_order": "desc",
        "offset": offset,
        "extend": True,
        "listing_source": "direct-search",
        "filters": {
            "category": {"id": IMMO_CAT},
            "location": {"regions": [IDF_REGION]},
            "enums": {
                "ad_type": ["offer"],
                "real_estate_type": ["1", "5"],
            },
            "ranges": {
                "price": {"min": PRIX_MIN, "max": PRIX_MAX},
            },
            "keywords": {"text": keyword, "type": "all"},
        },
    }
    try:
        resp = SESSION.post(
            "https://api.leboncoin.fr/finder/search",
            headers=headers,
            json=payload,
            timeout=15,
        )
        print(f"[LBC] {keyword} → HTTP {resp.status_code}")
        if resp.status_code == 200:
            return resp.json().get("ads", [])
        return []
    except Exception as e:
        print(f"[LBC] {keyword} → erreur: {e}")
        return []

def parse_ad(ad):
    try:
        prix_list = ad.get("price", [0])
        prix = prix_list[0] if prix_list else 0
        if not (PRIX_MIN <= prix <= PRIX_MAX):
            return None
        loc     = ad.get("location", {})
        ville   = loc.get("city", loc.get("region_name", "Île-de-France"))
        attrs   = {a["key"]: a.get("value_label", a.get("value", "")) for a in ad.get("attributes", [])}
        surface = 0
        try: surface = int(attrs.get("square", 0))
        except: pass
        return {
            "id":      ad.get("list_id"),
            "titre":   ad.get("subject", ""),
            "desc":    ad.get("body", ""),
            "prix":    prix,
            "ville":   ville,
            "surface": surface,
            "date":    ad.get("first_publication_date", ""),
            "link":    ad.get("url", f"https://www.leboncoin.fr/annonces/{ad.get('list_id')}"),
            "image":   (ad.get("images") or {}).get("thumb_url", ""),
        }
    except Exception as e:
        print(f"[parse] erreur: {e}")
        return None

def scrape_all():
    global SESSION
    print("[scrape] Démarrage...")
    seen_ids = set()
    results  = []
    for kw in KEYWORDS:
        ads = search_lbc(kw)
        for ad in ads:
            ad_id = ad.get("list_id")
            if ad_id in seen_ids:
                continue
            seen_ids.add(ad_id)
            parsed = parse_ad(ad)
            if parsed:
                results.append(parsed)
        time.sleep(2)
    print(f"[scrape] {len(results)} annonces")
    if not results:
        print("[scrape] 0 résultats — recréation session")
        SESSION = make_session()
    return results

def refresh_cache():
    with _lock:
        try:
            data = scrape_all()
            if data:
                _cache["data"] = data
                _cache["ts"]   = time.time()
        except Exception as e:
            print(f"[cache] Erreur: {e}")

def auto_refresh():
    print("[thread] Démarré")
    while True:
        refresh_cache()
        time.sleep(CACHE_TTL)

# Démarrage du thread au niveau module (fonctionne avec gunicorn)
print("[module] Lancement thread scraping...")
_t = threading.Thread(target=auto_refresh, daemon=True)
_t.start()
print("[module] Thread lancé.")

@app.route("/")
def index():
    return send_file("index.html")

@app.route("/api/annonces")
def api_annonces():
    age = time.time() - _cache["ts"]
    return jsonify({
        "ok":       True,
        "count":    len(_cache["data"]),
        "age_min":  round(age / 60, 1),
        "annonces": _cache["data"],
    })

@app.route("/health")
def health():
    return jsonify({"status": "ok", "cached": len(_cache["data"])})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT)
