import os
import json
import time
import threading
from flask import Flask, jsonify, send_from_directory
from curl_cffi import requests as curl_requests

app = Flask(__name__, static_folder=".")

# ─── CONFIG ───────────────────────────────────────────────────────────────────
PORT       = int(os.environ.get("PORT", 3000))
CACHE_TTL  = 15 * 60  # 15 min
IDF_REGION = "12"     # Île-de-France
IMMO_CAT   = "9"      # Ventes immobilières
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

# ─── CACHE ────────────────────────────────────────────────────────────────────
_cache = {"data": [], "ts": 0, "lock": threading.Lock()}

# ─── SESSION curl_cffi (simule Chrome, bypass TLS fingerprinting) ─────────────
def make_session():
    s = curl_requests.Session(impersonate="chrome120")
    return s

SESSION = make_session()

# ─── APPEL API LEBONCOIN ──────────────────────────────────────────────────────
def search_lbc(keyword, offset=0, limit=35):
    headers = {
        "accept": "*/*",
        "accept-language": "fr-FR,fr;q=0.9,en;q=0.8",
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
                "real_estate_type": ["1", "5"],  # 1=maison, 5=autre (immeuble)
            },
            "ranges": {
                "price": {"min": PRIX_MIN, "max": PRIX_MAX},
            },
            "keywords": {
                "text": keyword,
                "type": "all",
            },
        },
    }

    try:
        resp = SESSION.post(
            "https://api.leboncoin.fr/finder/search",
            headers=headers,
            json=payload,
            timeout=15,
        )
        if resp.status_code == 200:
            return resp.json().get("ads", [])
        else:
            print(f"[LBC] {keyword} → HTTP {resp.status_code}")
            return []
    except Exception as e:
        print(f"[LBC] {keyword} → erreur: {e}")
        return []

# ─── PARSING ANNONCE ──────────────────────────────────────────────────────────
def parse_ad(ad):
    try:
        prix_list = ad.get("price", [0])
        prix = prix_list[0] if prix_list else 0
        if not (PRIX_MIN <= prix <= PRIX_MAX):
            return None

        loc = ad.get("location", {})
        ville = loc.get("city", loc.get("region_name", "Île-de-France"))
        dept = loc.get("department_id", "")

        attrs = {a["key"]: a.get("value_label", a.get("value", "")) for a in ad.get("attributes", [])}
        surface = 0
        try:
            surface = int(attrs.get("square", 0))
        except:
            pass

        return {
            "id":       ad.get("list_id"),
            "titre":    ad.get("subject", ""),
            "desc":     ad.get("body", ""),
            "prix":     prix,
            "ville":    ville,
            "dept":     dept,
            "surface":  surface,
            "date":     ad.get("first_publication_date", ""),
            "link":     ad.get("url", f"https://www.leboncoin.fr/annonces/{ad.get('list_id')}"),
            "image":    (ad.get("images") or {}).get("thumb_url", ""),
        }
    except Exception as e:
        print(f"[parse] erreur: {e}")
        return None

# ─── SCRAPING COMPLET ─────────────────────────────────────────────────────────
def scrape_all():
    print("[scrape] Démarrage scraping LeBonCoin...")
    seen_ids = set()
    results  = []

    for kw in KEYWORDS:
        ads = search_lbc(kw, offset=0, limit=35)
        for ad in ads:
            ad_id = ad.get("list_id")
            if ad_id in seen_ids:
                continue
            seen_ids.add(ad_id)
            parsed = parse_ad(ad)
            if parsed:
                results.append(parsed)
        time.sleep(1)  # pause entre requêtes

    print(f"[scrape] {len(results)} annonces récupérées")
    return results

# ─── REFRESH CACHE ────────────────────────────────────────────────────────────
def refresh_cache():
    global SESSION
    with _cache["lock"]:
        try:
            data = scrape_all()
            if data:
                _cache["data"] = data
                _cache["ts"]   = time.time()
                print(f"[cache] Mis à jour: {len(data)} annonces")
            else:
                # Si DataDome bloque, recréer la session
                print("[cache] Aucun résultat — recréation session")
                SESSION = make_session()
        except Exception as e:
            print(f"[cache] Erreur: {e}")

def auto_refresh():
    while True:
        refresh_cache()
        time.sleep(CACHE_TTL)

# ─── ROUTES ───────────────────────────────────────────────────────────────────
@app.route("/")
def index():
    return send_from_directory("public", "index.html")

@app.route("/api/annonces")
def api_annonces():
    age = time.time() - _cache["ts"]
    return jsonify({
        "ok":      True,
        "count":   len(_cache["data"]),
        "age_min": round(age / 60, 1),
        "annonces": _cache["data"],
    })

@app.route("/health")
def health():
    return jsonify({"status": "ok", "cached": len(_cache["data"])})

# ─── DÉMARRAGE ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    # Premier scraping au démarrage (en arrière-plan)
    t = threading.Thread(target=auto_refresh, daemon=True)
    t.start()
    app.run(host="0.0.0.0", port=PORT)
