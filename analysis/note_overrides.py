"""Lecture des NOTES libres de l'utilisateur pour corriger l'analyse.

L'utilisateur connaît souvent des éléments que l'annonce n'exprime pas
clairement (il a appelé l'agence, visité, etc.). Sa note prime alors sur ce
qui a été extrait de l'annonce. Exemple :

    « 90€/mois de charges de copropriété, environ 3000€ de ravalement de
      façade, rénové très récemment, libre d'occupation. »

en tire : charges 90 €/mois · +3000 € de travaux · état « bon » · bien libre
(donc Airbnb de nouveau possible). La note étant du texte libre, on repère
chaque montant en euros puis on le classe selon les mots qui l'entourent
(avant OU après), plutôt que par un ordre figé.
"""

import re
import unicodedata

from analysis.condition import estimate_condition


def _fold(s):
    s = unicodedata.normalize("NFKD", (s or "").lower())
    return "".join(c for c in s if not unicodedata.combining(c))


def _to_int(txt):
    s = re.sub(r"\s", "", txt or "").replace(",", ".")
    try:
        return int(float(s))
    except ValueError:
        return 0


# Un montant en euros + sa périodicité éventuelle (après le montant).
_MONTANT_EUR = re.compile(
    r"(\d[\d\s.,]{0,7})\s*(?:€|euros?|eur\b)\s*"
    r"(/?\s*mois|par\s+mois|mensuel\w*|/?\s*an|annuel\w*|par\s+an)?",
    re.I,
)

_CHARGES_MOTS = ("charge", "copropri", "cc", "syndic")
_TRAVAUX_MOTS = ("travaux", "ravalement", "facade", "toiture", "charpente",
                 "refection", "renovation a", "rénovation à", "chantier")
_LIBRE_MOTS = ("libre d'occupation", "libre de suite", "libre a la vente",
               "libre immediatement", "libre a la vente", "non loue", "non loué",
               "vacant", "bien libre", "actuellement libre", "libre de toute occupation")


def _periode_diviseur(unite, montant):
    u = (unite or "").lower()
    if "mois" in u or "mensuel" in u:
        return 1
    if "an" in u or "annuel" in u:
        return 12
    return 12 if montant >= 600 else 1   # sans indication : gros montant = annuel


def parse(note):
    """Retourne un dict d'overrides tirés de la note, vide si rien d'exploitable.
    Clés possibles : charges_mensuelles, loyer_reel, travaux_supplementaires,
    condition (dict état), libre (bool)."""
    note = note or ""
    if not note.strip():
        return {}
    low = _fold(note)
    ov = {}

    # Positions de tous les mots-clés (sur le texte sans accents), pour classer
    # chaque montant par le mot-clé le PLUS PROCHE — un même terme (« copro »)
    # peut sinon aimanter deux montants voisins.
    reperes = []  # (position, categorie)
    for cat, mots in (("charges", _CHARGES_MOTS), ("travaux", _TRAVAUX_MOTS),
                      ("loyer", ("loyer", "loue", "loué"))):
        for mot in mots:
            start = 0
            while True:
                i = low.find(_fold(mot), start)
                if i < 0:
                    break
                reperes.append((i, cat))
                start = i + 1

    for m in _MONTANT_EUR.finditer(note):
        montant = _to_int(m.group(1))
        if montant <= 0:
            continue
        pos = m.start()
        proches = [(abs(i - pos), cat) for i, cat in reperes if abs(i - pos) <= 35]
        if not proches:
            continue
        cat = min(proches)[1]
        if cat == "charges":
            ov["charges_mensuelles"] = round(montant / _periode_diviseur(m.group(2), montant))
        elif cat == "travaux":
            ov["travaux_supplementaires"] = ov.get("travaux_supplementaires", 0) + montant
        elif cat == "loyer":
            ov["loyer_reel"] = round(montant / _periode_diviseur(m.group(2), montant))

    if any(mot in low for mot in _LIBRE_MOTS):
        ov["libre"] = True

    # État : si la note contient des mots-clés d'état, ils priment sur l'annonce.
    cond = estimate_condition("", note)
    if cond.get("confiance") == "mots-clés":
        ov["condition"] = cond

    return ov


def apply_to_ad(ad):
    """Applique les overrides de la note (ad['note_texte']) sur une COPIE du
    dict annonce, prête à être passée aux stratégies. Retourne (ad, overrides)."""
    ad = dict(ad)
    ov = parse(ad.get("note_texte", ""))
    if not ov:
        return ad, {}
    if "charges_mensuelles" in ov:
        ad["charges_mensuelles"] = ov["charges_mensuelles"]
    if ov.get("libre"):
        ad["loyer_reel"] = None          # bien libre : Airbnb de nouveau possible
    elif "loyer_reel" in ov:
        ad["loyer_reel"] = ov["loyer_reel"]
    if "travaux_supplementaires" in ov:
        ad["travaux_supplementaires"] = ov["travaux_supplementaires"]
    if "condition" in ov:
        ad["condition_note"] = ov["condition"]
    ad["note_overrides"] = ov
    return ad, ov
