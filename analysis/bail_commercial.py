"""Détection des biens sous bail commercial (résidence de tourisme,
résidence étudiante, résidence services/seniors, EHPAD, LMNP géré…).

Enjeu : sur ces biens, c'est l'exploitant qui détient le bail. L'acquéreur
n'a **aucune main dessus** — il ne peut ni louer à un étudiant, ni faire de
la location courte durée l'été. La stratégie saisonnière est donc
inapplicable, et le seul loyer pertinent est celui **annoncé dans la
description**, pas une estimation de marché (qui serait trompeuse, en
général nettement supérieure au loyer réellement versé par l'exploitant).

Ce module détecte ces biens et extrait le loyer annoncé quand il figure
dans le texte.
"""

import re
import unicodedata


def _fold(s):
    """Minuscule sans accents, pour comparer « Studéa » à « studea »,
    « Résidence étudiante » à « residence etudiante », etc."""
    s = unicodedata.normalize("NFKD", (s or "").lower())
    return "".join(c for c in s if not unicodedata.combining(c))


# Termes qui impliquent un bail commercial / une gestion par exploitant.
MOTS_BAIL_COMMERCIAL = [
    "résidence de tourisme", "residence de tourisme",
    "résidence étudiante", "residence etudiante", "résidence étudiants", "residence etudiants",
    "résidence services", "residence services", "résidence de services", "residence de services",
    "résidence senior", "residence senior", "résidence seniors", "residence seniors",
    "résidence affaires", "residence affaires", "résidence d'affaires", "residence d'affaires",
    "résidence gérée", "residence geree", "résidence géré", "residence gere",
    "bail commercial", "baux commerciaux",
    "ehpad", "lmnp géré", "lmnp gere", "lmnp exploitant",
    "exploitant", "gestionnaire de résidence", "gestionnaire de residence",
    "loué à l'exploitant", "loue a l'exploitant",
    "résidence de vacances", "residence de vacances",
    "résidence hôtelière", "residence hoteliere",
    "lmnp",  # LMNP géré = quasi toujours sous bail commercial d'exploitant
]

# Noms d'exploitants de résidences gérées : souvent seuls présents dans le
# TITRE (la description, elle, n'est pas toujours aspirée depuis la liste),
# ils suffisent à reconnaître un bien sous bail commercial.
EXPLOITANTS = [
    "belambra", "pierre & vacances", "pierre et vacances", "pierre&vacances",
    "odalys", "lagrange", "néméa", "nemea", "goélia", "goelia", "maeva",
    "vacancéole", "vacanceole", "cerise", "zenitude", "terresens", "réside études",
    "reside etudes", "les senioriales", "domitys", "les girandières", "les girandieres",
    "cardinal campus", "nexity studea", "studea", "suitétudes", "suitetudes",
    "appart'city", "appart city", "residhome", "residhotel", "resideal",
]

# Un simple "loué" ou "bail en cours" ne suffit pas : ce sont des biens
# classiques occupés, où l'on récupère la main au terme du bail.

# Montants : on cherche le loyer annoncé et sa périodicité. Le montant peut
# être suivi du symbole « € » comme du mot « euros » (fréquent sur ces
# annonces : « 2497,36 euros HT »).
# Milliers correctement groupés par 3 OU nombre simple, décimale optionnelle.
# On n'accepte PAS « 2028 614 » comme un seul montant (année + loyer accolés).
_MONTANT = r"(?<![\d.,])((?:\d{1,3}(?:[   .]\d{3})+|\d{1,7})(?:,\d{1,2})?)"
_EUR = r"(?:€|euros?|eur\b)"

PATTERNS_LOYER = [
    # « loyer annuel de 4 800 € », « loyers annuels : 2497,36 euros HT »
    (re.compile(rf"loyers?\s+annuel\w*[^\d€]{{0,25}}{_MONTANT}\s*{_EUR}", re.I), "an"),
    (re.compile(rf"loyers?[^\d€]{{0,25}}{_MONTANT}\s*{_EUR}\s*(?:HT\s*)?(?:/|par\s+)an", re.I), "an"),
    (re.compile(rf"{_MONTANT}\s*{_EUR}\s*(?:HT\s*)?(?:/|par\s+)an", re.I), "an"),
    # « loyer mensuel de 400 € », « loyer : 400 €/mois »
    (re.compile(rf"loyers?\s+mensuel\w*[^\d€]{{0,25}}{_MONTANT}\s*{_EUR}", re.I), "mois"),
    (re.compile(rf"loyers?[^\d€]{{0,25}}{_MONTANT}\s*{_EUR}\s*(?:HT\s*)?(?:/|par\s+)mois", re.I), "mois"),
    (re.compile(rf"{_MONTANT}\s*{_EUR}\s*(?:HT\s*)?(?:/|par\s+)mois", re.I), "mois"),
    # « loyer trimestriel de 1 200 € »
    (re.compile(rf"loyers?\s+trimestriel\w*[^\d€]{{0,25}}{_MONTANT}\s*{_EUR}", re.I), "trimestre"),
    # Dernier recours : « loyer de 4 800 € » sans périodicité explicite
    (re.compile(rf"loyers?[^\d€]{{0,25}}{_MONTANT}\s*{_EUR}", re.I), "inconnu"),
]

PATTERN_RENTABILITE = re.compile(r"rentabilit[ée][^\d]{0,20}(\d{1,2}[.,]?\d{0,2})\s*%", re.I)

DIVISEUR = {"an": 12, "trimestre": 3, "mois": 1}


def _to_number(txt):
    """Convertit un montant français en entier d'euros. Gère les milliers
    (« 4 800 », « 4.800 ») ET la décimale (« 2497,36 » → 2497, « 45,5 » → 45)
    sans confondre les deux — sinon « 2497,36 » deviendrait 249 736."""
    s = re.sub(r"\s", "", txt or "")        # milliers séparés par une espace
    s = re.sub(r"[.,]\d{1,2}$", "", s)      # décimale finale (1-2 chiffres) tronquée
    s = re.sub(r"[^\d]", "", s)             # milliers restants (point/virgule)
    return int(s) if s else 0


def detect(titre="", desc="", prix=0):
    """Retourne un dict décrivant la contrainte de bail commercial.

    `sous_bail_commercial` False = bien classique, les stratégies normales
    s'appliquent. True = l'acquéreur n'a pas la main sur le bail.
    """
    text = f"{titre or ''} {desc or ''}"
    low = _fold(text)

    # Comparaison sans accents des deux côtés (« Studéa » ↔ « studea »).
    signaux = [m for m in MOTS_BAIL_COMMERCIAL if _fold(m) in low]
    signaux += [e for e in EXPLOITANTS if _fold(e) in low]
    if not signaux:
        return {"sous_bail_commercial": False}

    loyer_mensuel = None
    periodicite = None
    for pattern, unite in PATTERNS_LOYER:
        m = pattern.search(text)
        if not m:
            continue
        montant = _to_number(m.group(1))
        if montant <= 0:
            continue
        if unite == "inconnu":
            # Sans périodicité, on tranche par plausibilité : un montant
            # élevé est presque toujours un loyer annuel.
            unite = "an" if montant >= 3000 else "mois"
        loyer_mensuel = round(montant / DIVISEUR[unite])
        periodicite = unite
        break

    # Repli : certaines annonces ne donnent que la rentabilité annoncée.
    rentabilite = None
    if loyer_mensuel is None:
        m = PATTERN_RENTABILITE.search(text)
        if m and prix > 0:
            try:
                rentabilite = float(m.group(1).replace(",", "."))
                loyer_mensuel = round(prix * rentabilite / 100 / 12)
                periodicite = "déduit de la rentabilité annoncée"
            except ValueError:
                pass

    return {
        "sous_bail_commercial": True,
        "type_residence": signaux[0],
        "signaux": signaux[:3],
        "loyer_mensuel": loyer_mensuel,
        "periodicite_source": periodicite,
        "rentabilite_annoncee": rentabilite,
        "note": (
            f"Bien en {signaux[0]} : bail commercial détenu par l'exploitant — "
            "vous n'avez pas la main sur le bail (ni bail étudiant, ni location courte durée)."
        ),
    }
