"""Pondération de l'attractivité d'un bien, pour corréler l'estimation
(loyer longue durée, nuitée Airbnb, valeur de revente) à l'adresse RÉELLE et
au standing du bien — et non à une simple moyenne de commune.

Deux signaux, tous deux tirés de l'annonce elle-même :

1. POSITIONNEMENT PRIX/m² du bien vs la médiane locale des comparables (même
   commune, même nombre de pièces). Le marché price déjà l'adresse : un bien
   nettement au-dessus de la médiane est presque toujours mieux situé / plus
   qualitatif. On amortit fortement — un +30 % de prix ne donne pas +30 % de
   loyer, les rendements se compriment dans le haut de gamme.

2. SIGNAUX QUALITATIFS du titre/description : vue mer, dernier étage, terrasse,
   piscine, standing, proximité plage… (+) ; à rénover, rez-de-chaussée, axe
   passant, vis-à-vis, sombre, bruit… (−).

Résultat : un multiplicateur borné, appliqué aux estimations locatives, plus
la liste des facteurs retenus (pour l'afficher et rester transparent).
"""

import unicodedata


def _fold(s):
    s = unicodedata.normalize("NFKD", (s or "").lower())
    return "".join(c for c in s if not unicodedata.combining(c))


# (fragment recherché SANS accents, poids, libellé affiché). Tokens choisis
# pour ne pas se chevaucher (ex. « a renover » négatif vs « refait a neuf »
# positif — on n'utilise pas le « renove » nu, sous-chaîne de « renover »).
SIGNAUX_POSITIFS = [
    ("vue mer",            0.06, "vue mer"),
    ("vue sur mer",        0.06, "vue mer"),
    ("vue panoramique",    0.05, "vue panoramique"),
    ("vue degagee",        0.04, "vue dégagée"),
    ("plage a pied",       0.05, "plage à pied"),
    ("bord de mer",        0.05, "bord de mer"),
    ("front de mer",       0.05, "front de mer"),
    ("proche plage",       0.04, "proche plage"),
    ("dernier etage",      0.05, "dernier étage"),
    ("toit terrasse",      0.05, "toit-terrasse"),
    ("penthouse",          0.06, "penthouse"),
    ("rooftop",            0.05, "rooftop"),
    ("terrasse",           0.03, "terrasse"),
    ("piscine",            0.04, "piscine"),
    ("standing",           0.04, "standing"),
    ("haut de gamme",      0.05, "haut de gamme"),
    ("prestation",         0.03, "prestations soignées"),
    ("prestige",           0.04, "prestige"),
    ("refait a neuf",      0.03, "refait à neuf"),
    ("residence neuve",    0.03, "résidence neuve"),
    ("entierement renove", 0.03, "entièrement rénové"),
    ("plein sud",          0.02, "plein sud"),
    ("traversant",         0.02, "traversant"),
    ("lumineux",           0.02, "lumineux"),
    ("au calme",           0.02, "au calme"),
    ("quartier residentiel", 0.02, "quartier résidentiel"),
    ("climatis",           0.02, "climatisation"),
    ("parking",            0.02, "parking"),
    ("garage",             0.02, "garage"),
    ("balcon",             0.02, "balcon"),
    ("loggia",             0.02, "loggia"),
]

SIGNAUX_NEGATIFS = [
    ("a renover",          -0.05, "à rénover"),
    ("a moderniser",       -0.04, "à moderniser"),
    ("gros travaux",       -0.06, "gros travaux"),
    ("travaux a prevoir",  -0.05, "travaux à prévoir"),
    ("prevoir des travaux", -0.05, "travaux à prévoir"),
    ("rez de chaussee",    -0.05, "rez-de-chaussée"),
    ("rez-de-chaussee",    -0.05, "rez-de-chaussée"),
    ("route passante",     -0.06, "axe passant"),
    ("axe passant",        -0.06, "axe passant"),
    ("route nationale",    -0.05, "bord de nationale"),
    ("voie rapide",        -0.06, "voie rapide"),
    ("vis-a-vis",          -0.04, "vis-à-vis"),
    ("vis a vis",          -0.04, "vis-à-vis"),
    ("sous-sol",           -0.04, "sur sous-sol"),
    ("sombre",             -0.04, "sombre"),
    ("peu lumineux",       -0.04, "peu lumineux"),
    ("sans ascenseur",     -0.03, "sans ascenseur"),
    ("bruyant",            -0.05, "bruyant"),
    ("nuisance",           -0.05, "nuisances"),
    ("copropriete degradee", -0.06, "copropriété dégradée"),
    ("procedure",          -0.04, "procédure en cours"),
    ("servitude",          -0.03, "servitude"),
]

# Bornes : on ne veut ni euphorie ni pénalité démesurée sur un mot.
_SIGNAUX_MIN, _SIGNAUX_MAX = -0.20, 0.20
_PRIX_MIN, _PRIX_MAX = 0.82, 1.22
_MULT_MIN, _MULT_MAX = 0.70, 1.40
# Amortissement du positionnement prix : +X % de prix -> +0,35·X % de loyer.
_AMORTI_PRIX = 0.35


def _clamp(x, lo, hi):
    return max(lo, min(hi, x))


def facteur_prix(prix_m2, median_m2):
    """Facteur lié au positionnement prix/m² vs la médiane locale. 1.0 si on
    n'a pas de médiane fiable."""
    if not prix_m2 or not median_m2 or median_m2 <= 0:
        return 1.0, None
    ratio = prix_m2 / median_m2
    facteur = _clamp(1 + _AMORTI_PRIX * (ratio - 1), _PRIX_MIN, _PRIX_MAX)
    return facteur, ratio


def facteur_signaux(titre, desc):
    """Somme bornée des signaux qualitatifs trouvés, + la liste des libellés
    (dédupliqués, sans doublon de libellé)."""
    texte = _fold(f"{titre or ''} {desc or ''}")
    poids = 0.0
    facteurs = []
    vus = set()
    for frag, w, label in SIGNAUX_POSITIFS + SIGNAUX_NEGATIFS:
        if frag in texte and label not in vus:
            poids += w
            vus.add(label)
            facteurs.append({"label": label, "sens": "+" if w > 0 else "-"})
    poids = _clamp(poids, _SIGNAUX_MIN, _SIGNAUX_MAX)
    return 1 + poids, facteurs


def evaluer(titre, desc, prix_m2, median_m2):
    """Multiplicateur d'attractivité global + détail. À appliquer aux
    estimations de loyer / nuitée. Toujours borné à [0.70, 1.40]."""
    fp, ratio = facteur_prix(prix_m2, median_m2)
    fs, facteurs = facteur_signaux(titre, desc)
    mult = _clamp(fp * fs, _MULT_MIN, _MULT_MAX)
    positionnement_pct = round((ratio - 1) * 100) if ratio is not None else None
    return {
        "multiplicateur": round(mult, 3),
        "facteur_prix": round(fp, 3),
        "facteur_signaux": round(fs, 3),
        "positionnement_prix_pct": positionnement_pct,  # +18 = 18% au-dessus de la médiane locale
        "facteurs": facteurs,
    }
