from simulateur_pret_reste_a_vivre_v3 import BAREME_IR_2026

def calcul_impot_bareme(revenu_imposable_annuel, parts):
    """Impôt brut annuel par la méthode du quotient familial (hors décote, réductions et crédits d'impôt)."""
    if revenu_imposable_annuel <= 0 or parts <= 0:
        return 0.0

    quotient = revenu_imposable_annuel / parts
    impot_par_part = 0.0
    borne_precedente = 0.0

    for borne, taux in BAREME_IR_2026:
        if quotient <= borne_precedente:
            break
        tranche_imposable = min(quotient, borne) - borne_precedente
        impot_par_part += tranche_imposable * taux
        borne_precedente = borne

    return impot_par_part * parts


if __name__ == '__main__':
    revenu_brut = 60000 + 100000
    parts = 2
    impot = calcul_impot_bareme(revenu_brut, parts)
    print(f"Impôt brut annuel pour un revenu imposable de {revenu_brut} € et {parts} parts : {impot:.2f} €")
    parts = 3 
    impot = calcul_impot_bareme(revenu_brut, parts)
    print(f"Impôt brut annuel pour un revenu imposable de {revenu_brut} € et {parts} parts : {impot:.2f} €")
    