"""Stratégie 1 — location saisonnière hybride : bail étudiant (longue durée,
hors saison) + Airbnb l'été. Pensée pour studios/T2, zone Sophia-Antipolis /
Villeneuve-Loubet où la demande étudiante et touristique coexistent.

L'estimation (loyer longue durée et nuitée Airbnb) est pondérée par
l'attractivité RÉELLE du bien (positionnement prix/m² vs marché local +
signaux de la description), afin de coller à l'adresse et non à une moyenne
de commune. Les revenus Airbnb sont comptés NETS de frais (conciergerie,
ménage, plateforme : au moins 25 %).
"""

from config import (
    LEASE_ETUDIANT_MOIS, AIRBNB_MOIS, TAUX_OCCUPATION_AIRBNB, AIRBNB_FRAIS_PCT,
    LOCATION_SAISONNIERE_SURFACE_MAX, CHARGES_NON_RECUP_PCT,
)
from references import get_reference, loyer_mensuel_estime, airbnb_nuit_estimee
from analysis.condition import estimate_condition
from analysis.bail_commercial import detect as detect_bail_commercial
from analysis import attractivite as attractivite_mod
from strategies.common import cout_acquisition

MULTIPLICATEUR_LOYER_ETUDIANT = 1.08  # meublé bail court vs. nu classique


def charges_non_recup(ad):
    """Charges de copropriété non récupérables sur le locataire (déduites du
    cash-flow), ou 0 si l'annonce ne les indique pas."""
    c = ad.get("charges_mensuelles")
    return round((c or 0) * CHARGES_NON_RECUP_PCT)


def calcul_attractivite(ad, marche):
    """Multiplicateur d'attractivité du bien à partir du marché local fourni
    (médianes prix/m² par ville+pièces)."""
    surface = ad.get("surface") or 0
    prix = ad.get("prix") or 0
    prix_m2 = (prix / surface) if surface > 0 else None
    median_m2 = (marche or {}).get(((ad.get("ville") or "").strip().lower(), ad.get("pieces")))
    return attractivite_mod.evaluer(ad.get("titre", ""), ad.get("desc", ""), prix_m2, median_m2)


def evaluate(ad, marche=None):
    prix = ad.get("prix") or 0
    surface = ad.get("surface") or 0
    pieces = ad.get("pieces")
    ville = ad.get("ville", "")

    condition = estimate_condition(ad.get("titre", ""), ad.get("desc", ""), ad.get("dpe"))
    cout_travaux = round(surface * condition["cost_m2"])
    acquisition = cout_acquisition(prix, cout_travaux)
    investissement = acquisition["investissement_total"]
    mensualite = acquisition["mensualite_credit"]

    ref = get_reference(ville)
    attr = calcul_attractivite(ad, marche)
    mult = attr["multiplicateur"]
    bail = detect_bail_commercial(ad.get("titre", ""), ad.get("desc", ""), prix)
    charges = charges_non_recup(ad)

    # Bien sous bail commercial : l'exploitant détient le bail, la stratégie
    # bail étudiant + Airbnb est inapplicable. Le loyer annoncé fait foi ; à
    # défaut, estimation de marché (pondérée, clairement signalée).
    if bail["sous_bail_commercial"]:
        loyer_reel = bail.get("loyer_mensuel")
        if loyer_reel:
            loyer_source = "loyer annoncé (bail commercial)"
        elif surface > 0:
            loyer_reel = round(loyer_mensuel_estime(surface, ref, mult))
            loyer_source = "estimation marché (loyer exploitant non précisé)"
        else:
            loyer_source = "loyer non précisé"
        revenu_annuel = (loyer_reel or 0) * 12
        revenu_mensuel_moyen = loyer_reel or 0
        rendement_brut = (
            round(revenu_annuel / investissement * 100, 1) if investissement > 0 and loyer_reel else 0
        )
        return {
            "eligibilite": "bail_commercial",
            "bail_commercial": bail,
            "condition": condition,
            "attractivite": attr,
            "cout_travaux": cout_travaux,
            "frais_notaire": acquisition["frais_notaire"],
            "investissement_total": investissement,
            "apport": acquisition["apport"],
            "mensualite_credit": mensualite,
            "loyer_etudiant_mensuel": None,
            "loyer_source": loyer_source,
            "airbnb_nuit_estime": None,
            "airbnb_revenu_mensuel_ete": None,
            "revenu_annuel_estime": revenu_annuel,
            "revenu_mensuel_moyen": revenu_mensuel_moyen,
            "rendement_brut_pct": rendement_brut,
            "charges_mensuelles": ad.get("charges_mensuelles"),
            "charges_non_recup": charges,
            "cashflow_mensuel_moyen": revenu_mensuel_moyen - mensualite - charges,
        }

    # Part longue durée (bail étudiant). Loyer réel s'il est indiqué, sinon
    # estimation pondérée par l'attractivité.
    if ad.get("loyer_reel"):
        loyer_etudiant_mensuel = ad["loyer_reel"]
        loyer_source = "loyer indiqué dans l'annonce"
    else:
        loyer_etudiant_mensuel = round(loyer_mensuel_estime(surface, ref, mult) * MULTIPLICATEUR_LOYER_ETUDIANT)
        loyer_source = "estimation marché pondérée (attractivité)"

    # Part Airbnb été, NETTE de frais (conciergerie/ménage/plateforme).
    airbnb_nuit = airbnb_nuit_estimee(surface, ref, mult)
    airbnb_ca_mensuel_ete = round(airbnb_nuit * 30 * TAUX_OCCUPATION_AIRBNB)
    airbnb_net_mensuel_ete = round(airbnb_ca_mensuel_ete * (1 - AIRBNB_FRAIS_PCT))

    revenu_annuel = loyer_etudiant_mensuel * LEASE_ETUDIANT_MOIS + airbnb_net_mensuel_ete * AIRBNB_MOIS
    revenu_mensuel_moyen = round(revenu_annuel / 12)

    rendement_brut = round(revenu_annuel / investissement * 100, 1) if investissement > 0 else 0
    cashflow_mensuel = revenu_mensuel_moyen - mensualite - charges

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
        "attractivite": attr,
        "cout_travaux": cout_travaux,
        "frais_notaire": acquisition["frais_notaire"],
        "investissement_total": investissement,
        "apport": acquisition["apport"],
        "mensualite_credit": mensualite,
        "loyer_etudiant_mensuel": loyer_etudiant_mensuel,
        "loyer_source": loyer_source,
        "airbnb_nuit_estime": airbnb_nuit,
        "airbnb_ca_mensuel_ete": airbnb_ca_mensuel_ete,     # brut (avant frais)
        "airbnb_revenu_mensuel_ete": airbnb_net_mensuel_ete,  # net de frais
        "airbnb_frais_pct": AIRBNB_FRAIS_PCT,
        "airbnb_occupation": TAUX_OCCUPATION_AIRBNB,
        "airbnb_mois": AIRBNB_MOIS,
        "lease_etudiant_mois": LEASE_ETUDIANT_MOIS,
        "revenu_annuel_estime": revenu_annuel,
        "revenu_mensuel_moyen": revenu_mensuel_moyen,
        "rendement_brut_pct": rendement_brut,
        "charges_mensuelles": ad.get("charges_mensuelles"),
        "charges_non_recup": charges,
        "cashflow_mensuel_moyen": cashflow_mensuel,
    }
