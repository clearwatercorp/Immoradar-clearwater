"""Estimation heuristique du potentiel de division d'une maison en
plusieurs logements — pour la stratégie marchand de biens.

Consigne explicite : on écarte les maisons isolées à diviser (accès,
viabilisation, revente compliqués) et on privilégie les maisons de ville /
mitoyennes, plus simples à scinder en lots indépendants.
"""

from config import DIVISION_SURFACE_MIN

MOTS_POSITIFS = [
    "maison de ville", "maison mitoyenne", "duplex", "deux logements", "2 logements",
    "entrée indépendante", "entree independante", "possibilité de division",
    "possibilite de division", "division possible", "r+1", "r+2", "studio indépendant",
    "studio independant", "appartement indépendant", "appartement independant",
    "garage aménageable", "garage amenageable", "sous-sol aménageable",
]
MOTS_ISOLEMENT = [
    "hameau", "en pleine campagne", "pleine campagne", "isolée en pleine nature",
    "isolee en pleine nature", "aucun voisinage", "loin de tout", "domaine privé",
    "domaine prive", "accès par chemin", "acces par chemin", "bois et forêt",
    "bois et foret", "sans voisin",
]


def _match(text, mots):
    return [m for m in mots if m in text]


def estimate_divisibilite(titre="", desc="", type_bien="", surface=0):
    if (type_bien or "").lower() != "maison":
        return {"potentiel": False, "note": "Appartement — division non pertinente"}

    text = f"{titre or ''} {desc or ''}".lower()

    isolement = _match(text, MOTS_ISOLEMENT)
    if isolement:
        return {"potentiel": False, "note": f"Maison isolée détectée ({isolement[0]}) — division écartée"}

    if surface and surface < DIVISION_SURFACE_MIN:
        return {"potentiel": False, "note": f"Surface {surface} m² < {DIVISION_SURFACE_MIN} m² — division peu rentable"}

    signaux = _match(text, MOTS_POSITIFS)
    if signaux:
        return {"potentiel": True, "note": f"Signaux positifs : {', '.join(signaux[:3])}"}

    if surface and surface >= DIVISION_SURFACE_MIN:
        return {"potentiel": "peut-être", "note": "Maison de surface suffisante, en ville — à vérifier sur plan"}

    return {"potentiel": False, "note": "Surface inconnue — division non évaluable"}
