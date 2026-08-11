import time
import threading

from flask import Flask, jsonify, send_file
from scrapfly import ScrapflyClient

import config
import storage
from scrapers import leboncoin, bienici, pap, seloger
from scrapers.common import passes_filters

app = Flask(__name__)

_client = ScrapflyClient(key=config.SCRAPFLY_KEY) if config.SCRAPFLY_KEY else None
_lock   = threading.Lock()
_status = {"ts": 0, "sources": {}}

SCRAPERS = {
    "Leboncoin": leboncoin.search,
    "Bien'ici":  bienici.search,
    "PAP":       pap.search,
    "SeLoger":   seloger.search,
}

storage.init_db()


def refresh_cache():
    with _lock:
        print(f"[refresh] Démarrage... (Scrapfly: {'oui' if _client else 'non'})")
        all_ads = []
        sources_status = {}
        for name, fn in SCRAPERS.items():
            try:
                ads = fn(_client)
                kept = [a for a in ads if a and passes_filters(a)]
                sources_status[name] = {"ok": True, "trouvees": len(ads), "retenues": len(kept)}
                all_ads.extend(kept)
                print(f"[{name}] {len(ads)} trouvées → {len(kept)} retenues après filtres")
            except Exception as e:
                sources_status[name] = {"ok": False, "error": str(e)}
                print(f"[{name}] erreur inattendue: {e}")

        new_ids = storage.upsert_ads(all_ads)
        _status["ts"] = time.time()
        _status["sources"] = sources_status
        print(f"[refresh] {len(all_ads)} annonces au total, {len(new_ids)} nouvelles")


def auto_refresh():
    print("[thread] Démarré")
    while True:
        try:
            refresh_cache()
        except Exception as e:
            print(f"[thread] erreur: {e}")
        time.sleep(config.CACHE_TTL)


print("[module] Lancement thread scraping...")
_t = threading.Thread(target=auto_refresh, daemon=True)
_t.start()
print("[module] Thread lancé.")


@app.route("/")
def index():
    return send_file("index.html")


@app.route("/api/annonces")
def api_annonces():
    now = time.time()
    ads = storage.get_all_ads()
    for a in ads:
        a["nouveau"] = (now - a["first_seen"]) < config.NEW_WINDOW_H * 3600
    age_min = round((now - _status["ts"]) / 60, 1) if _status["ts"] else None
    return jsonify({
        "ok":       True,
        "count":    len(ads),
        "age_min":  age_min,
        "sources":  _status["sources"],
        "annonces": ads,
    })


@app.route("/api/meta")
def api_meta():
    return jsonify({
        "center":       {"lat": config.CENTER_LAT, "lon": config.CENTER_LON},
        "radius_km":    config.RADIUS_KM,
        "ville_centre": config.VILLE_CENTRE,
        "surface_min":  config.SURFACE_MIN,
        "price_max":    config.PRICE_MAX,
        "rooms_min":    config.ROOMS_MIN,
        "refresh_min":  config.CACHE_TTL // 60,
    })


@app.route("/health")
def health():
    return jsonify({
        "status":   "ok",
        "cached":   len(storage.get_all_ads()),
        "scrapfly": bool(_client),
        "sources":  _status["sources"],
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=config.PORT)
