"""Stratégie 1 — location saisonnière hybride : bail étudiant (longue durée,
hors saison) + Airbnb l'été. Pensée pour studios/T2, zone Sophia-Antipolis /
Villeneuve-Loubet où la demande étudiante et touristique coexistent.
"""

from config import (
    LEASE_ETUDIANT_MOIS, AIRBNB_MOIS, TAUX_OCCUPATION_AIRBNB,
    LOCATION_SAISONNIERE_SURFACE_MAX, CHARGES_NON_RECUP_PCT,
)
from references import get_reference, loyer_mensuel_estime, airbnb_nuit_estimee
from analysis.condition import estimate_condition
from analysis.bail_commercial import detect as detect_bail_commercial
from strategies.common import cout_acquisition

MULTIPLICATEUR_LOYER_ETUDIANT = 1.08  # meublé bail court vs. nu classique


def charges_non_recup(ad):
    """Charges de copropriété non récupérables sur le locataire (déduites du
    cash-flow), ou 0 si l'annonce ne les indique pas."""
    c = ad.get("charges_mensuelles")
    return round((c or 0) * CHARGES_NON_RECUP_PCT)


def evaluate(ad):
    prix = ad.get("prix") or 0
    surface = ad.get("surface") or 0
    pieces = ad.get("pieces")
    ville = ad.get("ville", "")

    condition = estimate_condition(ad.get("titre", ""), ad.get("desc", ""), ad.get("dpe"))
    cout_travaux = round(surface * condition["cost_m2"])
    acquisition = cout_acquisition(prix, cout_travaux)
    investissement = acquisition["investissement_total"]

    bail = detect_bail_commercial(ad.get("titre", ""), ad.get("desc", ""), prix)
    charges = charges_non_recup(ad)

    # Bien sous bail commercial (résidence de tourisme/étudiante/services) :
    # l'exploitant détient le bail, la stratégie bail étudiant + Airbnb est
    # inapplicable. Seul le loyer annoncé dans l'annonce fait foi.
    if bail["sous_bail_commercial"]:
        loyer_reel = bail.get("loyer_mensuel")
        revenu_annuel = (loyer_reel or 0) * 12
        revenu_mensuel_moyen = loyer_reel or 0
        rendement_brut = (
            round(revenu_annuel / investissement * 100, 1) if investissement > 0 and loyer_reel else 0
        )
        return {
            "eligibilite": "bail_commercial",
            "bail_commercial": bail,
            "condition": condition,
            "cout_travaux": cout_travaux,
            "frais_notaire": acquisition["frais_notaire"],
            "investissement_total": investissement,
            "apport": acquisition["apport"],
            "mensualite_credit": acquisition["mensualite_credit"],
            "loyer_etudiant_mensuel": None,
            "airbnb_nuit_estime": None,
            "airbnb_revenu_mensuel_ete": None,
            "revenu_annuel_estime": revenu_annuel,
            "revenu_mensuel_moyen": revenu_mensuel_moyen,
            "rendement_brut_pct": rendement_brut,
            "charges_mensuelles": ad.get("charges_mensuelles"),
            "cashflow_mensuel_moyen": revenu_mensuel_moyen - acquisition["mensualite_credit"] - charges,
        }

    ref = get_reference(ville)
    loyer_etudiant_mensuel = round(loyer_mensuel_estime(surface, ref) * MULTIPLICATEUR_LOYER_ETUDIANT)
    airbnb_nuit = round(airbnb_nuit_estimee(surface, ref))
    revenu_airbnb_mensuel = round(airbnb_nuit * 30 * TAUX_OCCUPATION_AIRBNB)

    revenu_annuel = loyer_etudiant_mensuel * LEASE_ETUDIANT_MOIS + revenu_airbnb_mensuel * AIRBNB_MOIS
    revenu_mensuel_moyen = round(revenu_annuel / 12)

    rendement_brut = round(revenu_annuel / investissement * 100, 1) if investissement > 0 else 0
    cashflow_mensuel = revenu_mensuel_moyen - acquisition["mensualite_credit"] - charges

    if surface and surface <= LOCATION_SAISONNIERE_SURFACE_MAX and (not pieces or pieces <= 2):
        eligibilite = "bonne"
    elif surface and surface <= LOCATION_SAISONNIERE_SURFACE_MAX * 1.4:
        eligibilite = "limitee"
    else:
        eligibilite = "peu_adaptee"

    return {
        "eligibilite": eligibilite,
        "bail_commercial": bail,
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
        "charges_mensuelles": ad.get("charges_mensuelles"),
        "cashflow_mensuel_moyen": cashflow_mensuel,
    }
