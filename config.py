import os

# Zone de recherche : rayon (km) autour d'un point central — inchangée par
# rapport au monitoring locatif précédent.
CENTER_LAT   = float(os.environ.get("CENTER_LAT", 43.6486))
CENTER_LON   = float(os.environ.get("CENTER_LON", 7.1246))
RADIUS_KM    = float(os.environ.get("RADIUS_KM", 10))
VILLE_CENTRE = os.environ.get("VILLE_CENTRE", "Villeneuve-Loubet")

# Budget d'achat — pas de plafond imposé par défaut (filtrage affiné dans
# l'outil). PRICE_MAX_HARD_CAP écarte juste les biens d'exception qui ne
# collent à aucune des deux stratégies, pour éviter de polluer les résultats.
PRICE_MIN          = int(os.environ.get("PRICE_MIN", 0))
PRICE_MAX_HARD_CAP = int(os.environ.get("PRICE_MAX_HARD_CAP", 1_500_000))

PORT         = int(os.environ.get("PORT", 3000))
CACHE_TTL    = int(os.environ.get("CACHE_TTL", 15 * 60))
NEW_WINDOW_H = int(os.environ.get("NEW_WINDOW_H", 24))
DB_PATH      = os.environ.get("DB_PATH", "annonces.db")

# Scrapfly — service de scraping qui franchit DataDome/Cloudflare/PerimeterX
# via ses propres IP résidentielles. Palier GRATUIT permanent (1000 crédits/
# mois, sans carte). Mode recommandé en hébergement : coller ici la clé du
# compte gratuit (https://scrapfly.io) débloque Leboncoin, PAP et SeLoger.
# Laisser vide pour un scraping direct (Bien'ici seule en hébergement, les 4
# en local).
SCRAPFLY_KEY = os.environ.get("SCRAPFLY_KEY", "").strip()

# Proxy résidentiel/mobile — alternative à Scrapfly, indispensable pour Leboncoin, PAP et SeLoger
# depuis un hébergeur : leurs protections (DataDome, Cloudflare) bloquent les
# IP de datacenter dès la 1re requête, quelle que soit la finesse du scraping.
# Sans proxy, seule Bien'ici (non protégée) répond. Format standard :
#   http://utilisateur:motdepasse@hote:port   (ou socks5://…)
# Laisser vide pour ne pas utiliser de proxy.
PROXY_URL = os.environ.get("PROXY_URL", "").strip()

# ─── Frais d'acquisition / revente ────────────────────────────────────────
NOTAIRE_PCT        = float(os.environ.get("NOTAIRE_PCT", 0.075))   # frais de notaire, ancien
AGENCE_REVENTE_PCT = float(os.environ.get("AGENCE_REVENTE_PCT", 0.05))  # honoraires agence à la revente

# ─── Estimation travaux (heuristique v1, à remplacer par un modèle ML) ────
# €/m² selon l'état détecté par mots-clés dans le titre/la description.
TRAVAUX_COST_M2 = {
    "bon_etat":     150,   # peinture / petites finitions
    "a_rafraichir": 400,   # cuisine/SDB partielles, peinture, sols
    "a_renover":    900,   # rénovation complète (cuisine, SDB, élec, sols)
    "gros_travaux": 1500,  # structure, redistribution, mise aux normes lourde
}
# Défaut prudent quand aucun mot-clé d'état n'est détecté dans l'annonce.
TRAVAUX_COST_M2_DEFAUT = TRAVAUX_COST_M2["a_rafraichir"]

# Surface minimale (maison) en dessous de laquelle une division n'est pas
# jugée rentable, et mots-clés pour écarter les biens trop isolés.
DIVISION_SURFACE_MIN = int(os.environ.get("DIVISION_SURFACE_MIN", 90))

# ─── Location saisonnière (bail étudiant + Airbnb été) ────────────────────
# 8 mois de bail (environ octobre à mai) + 4 mois de location courte durée
# (juin à septembre) = 12 mois. Ajustable si le rythme réel diffère.
LEASE_ETUDIANT_MOIS = int(os.environ.get("LEASE_ETUDIANT_MOIS", 8))
AIRBNB_MOIS          = int(os.environ.get("AIRBNB_MOIS", 4))
TAUX_OCCUPATION_AIRBNB = float(os.environ.get("TAUX_OCCUPATION_AIRBNB", 0.75))
# Surface au-delà de laquelle le profil studio/T2 saisonnier devient moins pertinent.
LOCATION_SAISONNIERE_SURFACE_MAX = int(os.environ.get("LOCATION_SAISONNIERE_SURFACE_MAX", 55))

# ─── Financement (simulation crédit, pour le cash-flow) ───────────────────
CREDIT_TAUX_ANNUEL = float(os.environ.get("CREDIT_TAUX_ANNUEL", 0.037))
CREDIT_APPORT_PCT  = float(os.environ.get("CREDIT_APPORT_PCT", 0.15))
CREDIT_DUREE_ANS   = int(os.environ.get("CREDIT_DUREE_ANS", 20))

# Part des charges de copropriété non récupérable sur le locataire (le reste
# lui est refacturé). Déduite du cash-flow quand l'annonce indique les charges.
CHARGES_NON_RECUP_PCT = float(os.environ.get("CHARGES_NON_RECUP_PCT", 0.5))
