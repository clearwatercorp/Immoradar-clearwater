"""Communes de la zone surveillée (~10km autour de Villeneuve-Loubet, 06).

Sert à deux choses :
1. Restreindre les recherches sur les sites qui filtrent par commune plutôt
   que par rayon lat/lon (Leboncoin: city_zipcodes, SeLoger: inseeCodes,
   PAP/Bien'ici: identifiants internes résolus au démarrage).
2. Fournir une position de repli (centre de la commune) pour calculer une
   distance approximative quand l'annonce elle-même ne fournit pas de
   lat/lon (cas fréquent sur PAP, SeLoger, Bien'ici d'après leurs vraies
   structures de données).

⚠️ Codes INSEE/postaux saisis de mémoire, non vérifiés en direct (pas
d'accès à geo.api.gouv.fr depuis cet environnement) — à confirmer si un
site renvoie une erreur sur un identifiant de commune.
"""

COMMUNES = [
    {"nom": "Villeneuve-Loubet",   "cp": "06270", "insee": "06159", "lat": 43.6486, "lon": 7.1246},
    {"nom": "Cagnes-sur-Mer",      "cp": "06800", "insee": "06027", "lat": 43.6636, "lon": 7.1486},
    {"nom": "Antibes",             "cp": "06600", "insee": "06004", "lat": 43.5804, "lon": 7.1251},
    {"nom": "Biot",                "cp": "06410", "insee": "06017", "lat": 43.6250, "lon": 7.0930},
    {"nom": "Valbonne",            "cp": "06560", "insee": "06146", "lat": 43.6392, "lon": 7.0075},
    {"nom": "Vence",               "cp": "06140", "insee": "06157", "lat": 43.7229, "lon": 7.1128},
    {"nom": "Saint-Paul-de-Vence", "cp": "06570", "insee": "06126", "lat": 43.6969, "lon": 7.1219},
    {"nom": "La Colle-sur-Loup",   "cp": "06480", "insee": "06044", "lat": 43.6947, "lon": 7.1069},
    {"nom": "Roquefort-les-Pins",  "cp": "06330", "insee": "06103", "lat": 43.6656, "lon": 7.0453},
    {"nom": "Saint-Laurent-du-Var","cp": "06700", "insee": "06123", "lat": 43.6669, "lon": 7.1856},
]


def match_commune(ville="", cp=""):
    v = (ville or "").lower()
    c = (cp or "").strip()
    for commune in COMMUNES:
        if c and c == commune["cp"]:
            return commune
        if v and (commune["nom"].lower() in v or v in commune["nom"].lower()):
            return commune
    return None
