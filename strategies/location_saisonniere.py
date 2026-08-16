"""Stratégie 1 — location saisonnière hybride : bail étudiant (longue durée,
hors saison) + Airbnb l'été. Pensée pour studios/T2, zone Sophia-Antipolis /
Villeneuve-Loubet où la demande étudiante et touristique coexistent.
"""

from config import (
    LEASE_ETUDIANT_MOIS, AIRBNB_MOIS, TAUX_OCCUPATION_AIRBNB,
    LOCATION_SAISONNIERE_SURFACE_MAX,
)
from references import get_reference, loyer_mensuel_estime, airbnb_nuit_estimee
from analysis.condition import estimate_condition
from strategies.common import cout_acquisition

MULTIPLICATEUR_LOYER_ETUDIANT = 1.08  # meublé bail court vs. nu classique


def evaluate(ad):
    prix = ad.get("prix") or 0
    surface = ad.get("surface") or 0
    pieces = ad.get("pieces")
    ville = ad.get("ville", "")

    condition = estimate_condition(ad.get("titre", ""), ad.get("desc", ""))
    cout_travaux = round(surface * condition["cost_m2"])
    acquisition = cout_acquisition(prix, cout_travaux)

    ref = get_reference(ville)
    loyer_etudiant_mensuel = round(loyer_mensuel_estime(surface, ref) * MULTIPLICATEUR_LOYER_ETUDIANT)
    airbnb_nuit = round(airbnb_nuit_estimee(surface, ref))
    revenu_airbnb_mensuel = round(airbnb_nuit * 30 * TAUX_OCCUPATION_AIRBNB)

    revenu_annuel = loyer_etudiant_mensuel * LEASE_ETUDIANT_MOIS + revenu_airbnb_mensuel * AIRBNB_MOIS
    revenu_mensuel_moyen = round(revenu_annuel / 12)

    investissement = acquisition["investissement_total"]
    rendement_brut = round(revenu_annuel / investissement * 100, 1) if investissement > 0 else 0
    cashflow_mensuel = revenu_mensuel_moyen - acquisition["mensualite_credit"]

    if surface and surface <= LOCATION_SAISONNIERE_SURFACE_MAX and (not pieces or pieces <= 2):
        eligibilite = "bonne"
    elif surface and surface <= LOCATION_SAISONNIERE_SURFACE_MAX * 1.4:
        eligibilite = "limitee"
    else:
        eligibilite = "peu_adaptee"

    return {
        "eligibilite": eligibilite,
        "condition": condition,
        "cout_travaux": cout_travaux,
        "frais_notaire": acquisition["frais_notaire"],
        "investissement_total": investissement,
        "apport": acquisition["apport"],
        "mensualite_credit": acquisition["mensualite_credit"],
        "loyer_etudiant_mensuel": loyer_etudiant_mensuel,
        "airbnb_nuit_estime": airbnb_nuit,
        "airbnb_revenu_mensuel_ete": revenu_airbnb_mensuel,
        "revenu_annuel_estime": revenu_annuel,
        "revenu_mensuel_moyen": revenu_mensuel_moyen,
        "rendement_brut_pct": rendement_brut,
        "cashflow_mensuel_moyen": cashflow_mensuel,
    }
