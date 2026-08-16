"""Références de marché par ville, zone Villeneuve-Loubet (06).

⚠️ Ce sont des ORDRES DE GRANDEUR de départ (v1 heuristique), pas des
données mesurées — à affiner avec de vraies données (DVF, comparables
Airbnb/LeBonCoin réels) au fur et à mesure, en attendant le modèle ML
mentionné pour l'estimation état/travaux. Modifiable librement ci-dessous.

Champs par ville :
  prix_m2_revente   : prix de vente €/m² d'un bien en bon état après travaux
  loyer_m2_mensuel  : loyer nu/meublé classique longue durée, €/m²/mois
                       (les petites surfaces se louent plus cher au m², géré
                       via un coefficient dans strategies/*)
  airbnb_nuit_studio: nuitée moyenne haute saison pour un studio meublé
  airbnb_nuit_t2    : nuitée moyenne haute saison pour un T2 meublé
"""

REFERENCES = {
    "villeneuve-loubet":  {"prix_m2_revente": 4800, "loyer_m2_mensuel": 17, "airbnb_nuit_studio": 95,  "airbnb_nuit_t2": 135},
    "cagnes-sur-mer":     {"prix_m2_revente": 4600, "loyer_m2_mensuel": 17, "airbnb_nuit_studio": 90,  "airbnb_nuit_t2": 130},
    "antibes":            {"prix_m2_revente": 5200, "loyer_m2_mensuel": 18, "airbnb_nuit_studio": 100, "airbnb_nuit_t2": 145},
    "biot":               {"prix_m2_revente": 4700, "loyer_m2_mensuel": 17, "airbnb_nuit_studio": 85,  "airbnb_nuit_t2": 125},
    "valbonne":           {"prix_m2_revente": 5000, "loyer_m2_mensuel": 18, "airbnb_nuit_studio": 90,  "airbnb_nuit_t2": 130},
    "sophia-antipolis":   {"prix_m2_revente": 5000, "loyer_m2_mensuel": 18, "airbnb_nuit_studio": 90,  "airbnb_nuit_t2": 130},
    "vence":              {"prix_m2_revente": 4200, "loyer_m2_mensuel": 15, "airbnb_nuit_studio": 80,  "airbnb_nuit_t2": 115},
    "saint-paul-de-vence":{"prix_m2_revente": 5500, "loyer_m2_mensuel": 17, "airbnb_nuit_studio": 100, "airbnb_nuit_t2": 140},
    "saint-paul":         {"prix_m2_revente": 5500, "loyer_m2_mensuel": 17, "airbnb_nuit_studio": 100, "airbnb_nuit_t2": 140},
    "la colle-sur-loup":  {"prix_m2_revente": 4400, "loyer_m2_mensuel": 15, "airbnb_nuit_studio": 80,  "airbnb_nuit_t2": 115},
    "roquefort-les-pins": {"prix_m2_revente": 4300, "loyer_m2_mensuel": 15, "airbnb_nuit_studio": 75,  "airbnb_nuit_t2": 110},
    "saint-laurent-du-var":{"prix_m2_revente": 4700, "loyer_m2_mensuel": 17, "airbnb_nuit_studio": 90, "airbnb_nuit_t2": 130},
    "le rouret":          {"prix_m2_revente": 4300, "loyer_m2_mensuel": 15, "airbnb_nuit_studio": 75,  "airbnb_nuit_t2": 110},
    "opio":               {"prix_m2_revente": 4400, "loyer_m2_mensuel": 15, "airbnb_nuit_studio": 78,  "airbnb_nuit_t2": 112},
}

DEFAUT = {"prix_m2_revente": 4700, "loyer_m2_mensuel": 16, "airbnb_nuit_studio": 88, "airbnb_nuit_t2": 125}


def get_reference(ville):
    v = (ville or "").lower()
    for key, ref in REFERENCES.items():
        if key in v:
            return ref
    return DEFAUT


def loyer_mensuel_estime(surface, ref):
    """Loyer longue durée estimé : coefficient croissant au m² pour les
    petites surfaces (studio/T2), typique du marché locatif français."""
    m2 = ref["loyer_m2_mensuel"]
    if surface <= 25:
        m2 *= 1.35
    elif surface <= 40:
        m2 *= 1.15
    elif surface > 80:
        m2 *= 0.85
    return round(surface * m2)


def airbnb_nuit_estimee(surface, ref):
    if surface <= 30:
        return ref["airbnb_nuit_studio"]
    if surface <= 55:
        return ref["airbnb_nuit_t2"]
    # au-delà du T2, interpolation grossière (+12€ par tranche de 15m²)
    return round(ref["airbnb_nuit_t2"] + ((surface - 55) / 15) * 12)
