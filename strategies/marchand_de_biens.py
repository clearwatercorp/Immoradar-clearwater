"""Stratégie 2 — marchand de biens : achat (+division si pertinent) +
travaux + revente, ou alternative rendement locatif classique ("tension
locative") si la revente n'est pas assez marginale.
"""

from config import AGENCE_REVENTE_PCT
from references import get_reference, loyer_mensuel_estime
from analysis.condition import estimate_condition
from analysis.divisibilite import estimate_divisibilite
from strategies.common import cout_acquisition

NEGOCIATIONS = [0.05, 0.10, 0.15]


def _scenario_marge(prix, cout_travaux, valeur_apres_travaux, frais_revente):
    acquisition = cout_acquisition(prix, cout_travaux)
    investissement = acquisition["investissement_total"]
    marge = round(valeur_apres_travaux - frais_revente - investissement)
    marge_pct = round(marge / investissement * 100, 1) if investissement > 0 else 0
    return {"prix": round(prix), "investissement_total": investissement, "marge": marge, "marge_pct": marge_pct}


def evaluate(ad):
    prix = ad.get("prix") or 0
    surface = ad.get("surface") or 0
    ville = ad.get("ville", "")
    type_bien = ad.get("type_bien", "")

    condition = estimate_condition(ad.get("titre", ""), ad.get("desc", ""))
    cout_travaux = round(surface * condition["cost_m2"])
    acquisition = cout_acquisition(prix, cout_travaux)
    investissement = acquisition["investissement_total"]

    ref = get_reference(ville)
    valeur_apres_travaux = round(surface * ref["prix_m2_revente"])
    frais_revente = round(valeur_apres_travaux * AGENCE_REVENTE_PCT)

    scenario_actuel = _scenario_marge(prix, cout_travaux, valeur_apres_travaux, frais_revente)
    scenarios_negociation = [
        {"remise_pct": round(r * 100), **_scenario_marge(prix * (1 - r), cout_travaux, valeur_apres_travaux, frais_revente)}
        for r in NEGOCIATIONS
    ]

    divisibilite = estimate_divisibilite(ad.get("titre", ""), ad.get("desc", ""), type_bien, surface)

    loyer_classique_mensuel = round(loyer_mensuel_estime(surface, ref))
    rendement_locatif_brut = round(loyer_classique_mensuel * 12 / investissement * 100, 1) if investissement > 0 else 0
    mensualite = acquisition["mensualite_credit"]
    cashflow_locatif_mensuel = loyer_classique_mensuel - mensualite

    marge_pct = scenario_actuel["marge_pct"]
    marge_apres_nego10 = scenarios_negociation[1]["marge_pct"]
    if marge_pct >= 15 and rendement_locatif_brut >= 6:
        verdict = {"label": "Excellente opportunité", "priorite": 1}
    elif marge_pct >= 8 or rendement_locatif_brut >= 6:
        verdict = {"label": "Bonne opportunité", "priorite": 2}
    elif marge_apres_nego10 >= 8:
        verdict = {"label": "Intéressant avec négociation", "priorite": 3}
    else:
        verdict = {"label": "À surveiller", "priorite": 4}

    return {
        "verdict": verdict,
        "condition": condition,
        "cout_travaux": cout_travaux,
        "frais_notaire": acquisition["frais_notaire"],
        "investissement_total": investissement,
        "valeur_apres_travaux": valeur_apres_travaux,
        "frais_revente": frais_revente,
        "marge": scenario_actuel["marge"],
        "marge_pct": marge_pct,
        "scenarios_negociation": scenarios_negociation,
        "divisibilite": divisibilite,
        "loyer_classique_mensuel": loyer_classique_mensuel,
        "rendement_locatif_brut_pct": rendement_locatif_brut,
        "mensualite_credit": mensualite,
        "cashflow_locatif_mensuel": cashflow_locatif_mensuel,
    }
