"""Stratégie 2 — marchand de biens : achat (+division si pertinent) +
travaux + revente, ou alternative rendement locatif classique ("tension
locative") si la revente n'est pas assez marginale.
"""

from config import AGENCE_REVENTE_PCT
from references import get_reference, loyer_mensuel_estime
from analysis.condition import estimate_condition
from analysis.divisibilite import estimate_divisibilite
from analysis.bail_commercial import detect as detect_bail_commercial
from analysis import attractivite as attractivite_mod
from strategies.common import cout_acquisition

NEGOCIATIONS = [0.05, 0.10, 0.15]


def _scenario_marge(prix, cout_travaux, valeur_apres_travaux, frais_revente):
    acquisition = cout_acquisition(prix, cout_travaux)
    investissement = acquisition["investissement_total"]
    marge = round(valeur_apres_travaux - frais_revente - investissement)
    marge_pct = round(marge / investissement * 100, 1) if investissement > 0 else 0
    return {"prix": round(prix), "investissement_total": investissement, "marge": marge, "marge_pct": marge_pct}


def evaluate(ad, marche=None):
    prix = ad.get("prix") or 0
    surface = ad.get("surface") or 0
    ville = ad.get("ville", "")
    type_bien = ad.get("type_bien", "")

    # Note de l'utilisateur : peut corriger l'état et ajouter des travaux
    # (ravalement, toiture…) constatés hors annonce.
    condition = ad.get("condition_note") or estimate_condition(ad.get("titre", ""), ad.get("desc", ""), ad.get("dpe"))
    cout_travaux = round(surface * condition["cost_m2"]) + (ad.get("travaux_supplementaires") or 0)
    acquisition = cout_acquisition(prix, cout_travaux)
    investissement = acquisition["investissement_total"]

    ref = get_reference(ville)

    # Attractivité du bien (positionnement prix/m² + signaux description).
    prix_m2 = (prix / surface) if surface > 0 else None
    median_m2 = (marche or {}).get((ville.strip().lower(), ad.get("pieces")))
    attr = attractivite_mod.evaluer(ad.get("titre", ""), ad.get("desc", ""), prix_m2, median_m2)

    # Valeur de revente (bien rénové) : on l'ancre sur le MARCHÉ LOCAL RÉEL —
    # la médiane prix/m² des comparables — plutôt que sur une constante de
    # commune, car « acheter sous le marché » se mesure contre le vrai secteur.
    # On la module par les signaux qualitatifs (un bien mieux placé se revend
    # au-dessus de la médiane) SANS réutiliser le positionnement prix (ce serait
    # circulaire : la marge doit venir de l'écart au marché, pas du prix affiché).
    if median_m2:
        prix_m2_revente = median_m2 * attr["facteur_signaux"]
        revente_source = "médiane locale (comparables) ajustée qualité"
    else:
        prix_m2_revente = ref["prix_m2_revente"] * attr["facteur_signaux"]
        revente_source = "référence commune (peu de comparables) ajustée qualité"
    valeur_apres_travaux = round(surface * prix_m2_revente)
    frais_revente = round(valeur_apres_travaux * AGENCE_REVENTE_PCT)

    scenario_actuel = _scenario_marge(prix, cout_travaux, valeur_apres_travaux, frais_revente)
    scenarios_negociation = [
        {"remise_pct": round(r * 100), **_scenario_marge(prix * (1 - r), cout_travaux, valeur_apres_travaux, frais_revente)}
        for r in NEGOCIATIONS
    ]

    divisibilite = estimate_divisibilite(ad.get("titre", ""), ad.get("desc", ""), type_bien, surface)

    # Sous bail commercial, le loyer de marché n'a aucun sens : c'est
    # l'exploitant qui paie, au montant fixé par le bail. On utilise donc le
    # loyer annoncé dans la description quand il a pu être extrait.
    bail = detect_bail_commercial(ad.get("titre", ""), ad.get("desc", ""), prix)
    if bail["sous_bail_commercial"]:
        loyer_classique_mensuel = bail.get("loyer_mensuel") or 0
        if loyer_classique_mensuel:
            loyer_source = "loyer annoncé dans l'annonce (bail commercial)"
        elif surface > 0:
            # Loyer exploitant non précisé : on propose une estimation de
            # marché (pondérée, signalée), plutôt que de laisser le loyer vide.
            loyer_classique_mensuel = round(loyer_mensuel_estime(surface, ref, attr["multiplicateur"]))
            loyer_source = "estimation marché (loyer exploitant non précisé)"
        else:
            loyer_source = "loyer non mentionné dans l'annonce — à demander"
    elif ad.get("loyer_reel"):
        # Bien déjà loué / loyer indiqué : le vrai loyer prime sur l'estimation.
        loyer_classique_mensuel = ad["loyer_reel"]
        loyer_source = "loyer actuel indiqué dans l'annonce"
    else:
        loyer_classique_mensuel = round(loyer_mensuel_estime(surface, ref, attr["multiplicateur"]))
        loyer_source = "estimation marché local pondérée (attractivité)"

    from config import CHARGES_NON_RECUP_PCT
    charges = round((ad.get("charges_mensuelles") or 0) * CHARGES_NON_RECUP_PCT)
    rendement_locatif_brut = round(loyer_classique_mensuel * 12 / investissement * 100, 1) if investissement > 0 else 0
    mensualite = acquisition["mensualite_credit"]
    cashflow_locatif_mensuel = loyer_classique_mensuel - mensualite - charges

    marge_pct = scenario_actuel["marge_pct"]
    marge_apres_nego10 = scenarios_negociation[1]["marge_pct"]
    if bail["sous_bail_commercial"]:
        # Revente contrainte : l'acheteur suivant hérite du bail, le marché
        # est nettement plus étroit. On ne classe jamais ces biens en tête.
        verdict = {"label": "Bail commercial — à étudier", "priorite": 4}
    elif marge_pct >= 15 and rendement_locatif_brut >= 6:
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
        "attractivite": attr,
        "cout_travaux": cout_travaux,
        "frais_notaire": acquisition["frais_notaire"],
        "investissement_total": investissement,
        "valeur_apres_travaux": valeur_apres_travaux,
        "revente_source": revente_source,
        "frais_revente": frais_revente,
        "marge": scenario_actuel["marge"],
        "marge_pct": marge_pct,
        "scenarios_negociation": scenarios_negociation,
        "divisibilite": divisibilite,
        "bail_commercial": bail,
        "loyer_source": loyer_source,
        "charges_mensuelles": ad.get("charges_mensuelles"),
        "charges_non_recup": charges,
        "loyer_classique_mensuel": loyer_classique_mensuel,
        "rendement_locatif_brut_pct": rendement_locatif_brut,
        "mensualite_credit": mensualite,
        "cashflow_locatif_mensuel": cashflow_locatif_mensuel,
    }
