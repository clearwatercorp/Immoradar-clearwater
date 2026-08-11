import os

# Zone de recherche : rayon (km) autour d'un point central
CENTER_LAT   = float(os.environ.get("CENTER_LAT", 43.6486))
CENTER_LON   = float(os.environ.get("CENTER_LON", 7.1246))
RADIUS_KM    = float(os.environ.get("RADIUS_KM", 10))
VILLE_CENTRE = os.environ.get("VILLE_CENTRE", "Villeneuve-Loubet")

# Critères du bien recherché
SURFACE_MIN = int(os.environ.get("SURFACE_MIN", 35))
PRICE_MAX   = int(os.environ.get("PRICE_MAX", 1300))
ROOMS_MIN   = int(os.environ.get("ROOMS_MIN", 2))  # exclut les studios / T1

PORT         = int(os.environ.get("PORT", 3000))
CACHE_TTL    = int(os.environ.get("CACHE_TTL", 10 * 60))       # fréquence de re-scraping
NEW_WINDOW_H = int(os.environ.get("NEW_WINDOW_H", 24))         # fenêtre du badge "NOUVEAU"
SCRAPFLY_KEY = os.environ.get("SCRAPFLY_KEY", "")
DB_PATH      = os.environ.get("DB_PATH", "annonces.db")
