"""Estimation heuristique de l'état d'un bien et du coût de travaux associé,
à partir du titre/de la description de l'annonce.

v1 volontairement simple (mots-clés) — à remplacer plus tard par un modèle
entraîné sur photos/DPE/texte. En attendant, chaque résultat porte un champ
`confiance` pour distinguer un état détecté d'un état supposé par défaut.
"""

from config import TRAVAUX_COST_M2, TRAVAUX_COST_M2_DEFAUT

MOTS_GROS_TRAVAUX = [
    "à restaurer", "a restaurer", "à reconstruire", "gros œuvre", "gros oeuvre",
    "hors d'eau hors d'air", "insalubre", "aucun confort", "ruine", "très gros travaux",
    "entièrement à refaire", "corps de ferme à rénover",
]
MOTS_A_RENOVER = [
    "à rénover", "a renover", "travaux à prévoir", "travaux a prevoir",
    "rénovation à prévoir", "à moderniser", "a moderniser", "cuisine à refaire",
    "salle de bain à refaire", "gros potentiel", "à remettre au goût du jour intégralement",
    "chantier", "permis de construire",
]
MOTS_A_RAFRAICHIR = [
    "à rafraîchir", "a rafraichir", "à mettre au goût du jour", "a mettre au gout du jour",
    "quelques travaux", "décoration à revoir", "decoration a revoir", "peinture à prévoir",
    "sols à refaire", "quelques finitions",
]
MOTS_BON_ETAT = [
    "refait à neuf", "refait a neuf", "rénové récemment", "renove recemment",
    "aucun travaux", "aucuns travaux", "prestations haut de gamme", "construction récente",
    "construction recente", "tout confort", "récent", "recent", "neuf", "rénové",
    "renove", "moderne", "impeccable",
]


def _match(text, mots):
    return [m for m in mots if m in text]


def estimate_condition(titre="", desc=""):
    text = f"{titre or ''} {desc or ''}".lower()

    hits = _match(text, MOTS_GROS_TRAVAUX)
    if hits:
        return {"label": "Gros travaux", "cost_m2": TRAVAUX_COST_M2["gros_travaux"], "confiance": "mots-clés", "signaux": hits[:3]}

    hits = _match(text, MOTS_A_RENOVER)
    if hits:
        return {"label": "À rénover", "cost_m2": TRAVAUX_COST_M2["a_renover"], "confiance": "mots-clés", "signaux": hits[:3]}

    hits = _match(text, MOTS_A_RAFRAICHIR)
    if hits:
        return {"label": "À rafraîchir", "cost_m2": TRAVAUX_COST_M2["a_rafraichir"], "confiance": "mots-clés", "signaux": hits[:3]}

    hits = _match(text, MOTS_BON_ETAT)
    if hits:
        return {"label": "Bon état", "cost_m2": TRAVAUX_COST_M2["bon_etat"], "confiance": "mots-clés", "signaux": hits[:3]}

    return {"label": "État inconnu", "cost_m2": TRAVAUX_COST_M2_DEFAUT, "confiance": "estimation par défaut (prudente)", "signaux": []}
