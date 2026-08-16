from config import CREDIT_TAUX_ANNUEL, CREDIT_APPORT_PCT, CREDIT_DUREE_ANS, NOTAIRE_PCT


def mensualite_credit(montant_emprunte, taux_annuel=CREDIT_TAUX_ANNUEL, duree_ans=CREDIT_DUREE_ANS):
    if montant_emprunte <= 0:
        return 0
    tm = taux_annuel / 12
    n = duree_ans * 12
    if tm == 0:
        return montant_emprunte / n
    return montant_emprunte * (tm * (1 + tm) ** n) / ((1 + tm) ** n - 1)


def cout_acquisition(prix, cout_travaux, apport_pct=CREDIT_APPORT_PCT, taux_annuel=CREDIT_TAUX_ANNUEL, duree_ans=CREDIT_DUREE_ANS):
    """Coût total d'acquisition (prix + notaire + travaux) et simulation de
    financement associée (apport, emprunt, mensualité)."""
    frais_notaire = round(prix * NOTAIRE_PCT)
    investissement_total = prix + frais_notaire + cout_travaux
    apport = round(investissement_total * apport_pct)
    emprunt = investissement_total - apport
    mensualite = round(mensualite_credit(emprunt, taux_annuel, duree_ans))
    return {
        "frais_notaire": frais_notaire,
        "investissement_total": investissement_total,
        "apport": apport,
        "emprunt": emprunt,
        "mensualite_credit": mensualite,
    }
