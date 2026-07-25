import json
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

CONFIG_PATH = Path(__file__).with_name("dashboard_fusion_config.json")

DEPENSES_TEMPLATE = {
    "Logement & Énergies": [
        ("Taxe foncière", 1800.0, "Annuelle"),
        ("Électricité & Gaz", 120.0, "Mensuelle"),
        ("Eau", 35.0, "Mensuelle"),
        ("Charges de copropriété", 150.0, "Mensuelle"),
        ("Entretien & petits travaux", 50.0, "Mensuelle"),
    ],
    "Vie quotidienne & Alimentation": [
        ("Courses alimentaires", 550.0, "Mensuelle"),
        ("Restos, livraisons & sorties", 200.0, "Mensuelle"),
        ("Hygiène, pharmacie & entretien", 80.0, "Mensuelle"),
        ("Animaux de compagnie", 40.0, "Mensuelle"),
    ],
    "Transports": [
        ("Carburant / Recharge EV", 150.0, "Mensuelle"),
        ("Assurance auto / moto", 720.0, "Annuelle"),
        ("Transports en commun", 40.0, "Mensuelle"),
        ("Entretien auto & pneus", 400.0, "Annuelle"),
    ],
    "Abonnements & Services": [
        ("Box Internet & Téléphones", 60.0, "Mensuelle"),
        ("Streaming & médias", 30.0, "Mensuelle"),
        ("Sport, clubs & loisirs", 45.0, "Mensuelle"),
    ],
    "Assurances & Taxes hors immo": [
        ("Assurance habitation", 240.0, "Annuelle"),
        ("Mutuelle santé", 40.0, "Mensuelle"),
    ],
    "Enfants & Famille": [
        ("Frais de garde", 0.0, "Mensuelle"),
        ("Cantine & activités scolaires", 0.0, "Mensuelle"),
    ],
    "Plaisir & Projets": [
        ("Vacances & Voyages", 2400.0, "Annuelle"),
        ("Habillement & shopping", 100.0, "Mensuelle"),
    ],
}

DEFAULT_PARAMS = {
    "mode_simulation": "Mensualité",
    "revenu_1": 3000.0,
    "revenu_2": 2000.0,
    "autres_revenus": 0.0,
    "charges_fixes": 0.0,
    "prix_bien": 300000.0,
    "apport": 30000.0,
    "frais_notaire_pct": 8.0,
    "taux_credit": 3.5,
    "duree_principale": 25,
    "taux_assurance": 0.34,
    "taux_endettement": 35,
    "pret_comp_1_montant": 0.0,
    "pret_comp_1_taux": 1.0,
    "pret_comp_1_duree": 10,
    "pret_comp_2_montant": 0.0,
    "pret_comp_2_taux": 1.0,
    "pret_comp_2_duree": 10,
    "activer_pret_relais": False,
    "ancien_pret_crd": 150000.0,
    "prix_vente_estime": 300000.0,
    "facteur_revente_banque_pct": 70.0,
    "duree_relais_mois": 6,
    "taux_pret_relais": 4.0,
    "frais_annexes_montant": 3000.0,
    "taux_charges_sociales_pct": 23.0,
    "situation_couple": "Vie en couple",
    "declaration_commune": True,
    "nb_enfants": 0,
    "enfants_rev1": 0,
    "depenses_valeurs": {},
    "depenses_frequences": {},
}

# Barème progressif de l'impôt sur le revenu 2026 (applicable aux revenus 2025).
# À mettre à jour chaque année (loi de finances) : (borne_haute_tranche, taux_marginal)
BAREME_IR_2026 = [
    (11600.0, 0.0),
    (29579.0, 0.11),
    (84577.0, 0.30),
    (181917.0, 0.41),
    (float("inf"), 0.45),
]

ABATTEMENT_FRAIS_PRO_PCT = 0.10  # abattement forfaitaire simplifié de 10% (plafond/plancher réels ignorés)


def calcul_parts_fiscales(nb_adultes_declaration, nb_enfants):
    """Quotient familial simplifié (méthode générale, hors majoration 'parent isolé' / case T)."""
    parts = float(nb_adultes_declaration)
    enfants_demi_part = max(0,min(nb_enfants, 2))
    enfants_part_entiere = max(nb_enfants - 2, 0)
    parts += enfants_demi_part * 0.5 + enfants_part_entiere * 1.0
    return parts


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


def estimer_impot_mensuel(
    revenu_net_avant_impot_total,
    situation_couple,
    declaration_commune,
    nb_enfants,
    enfants_rev1,
    enfants_rev2,
    revenu_1,
    revenu_2,
    autres_revenus,
    taux_charges_sociales_pct,
):
    """Estime l'impôt sur le revenu mensuel du foyer et le nombre de parts fiscales.

    Simplifications assumées :
    - Abattement forfaitaire de 10% appliqué sans plafond/plancher.
    - Pas de décote, réductions ou crédits d'impôt.
    - Pas de majoration 'parent isolé' (case T).
    - En cas de déclarations séparées, les 'autres revenus' sont rattachés à Revenu 2.
    """

    def net_imposable_annuel(net_mensuel):
        return max(net_mensuel, 0.0) * 12 * (1 - ABATTEMENT_FRAIS_PRO_PCT)

    if situation_couple == "Vie en couple" and not declaration_commune:
        net_1 = revenu_1 * (1 - taux_charges_sociales_pct / 100)
        net_2 = (revenu_2 + autres_revenus) * (1 - taux_charges_sociales_pct / 100)
        parts_1 = calcul_parts_fiscales(1, enfants_rev1)
        parts_2 = calcul_parts_fiscales(1, enfants_rev2)
        impot_annuel = calcul_impot_bareme(net_imposable_annuel(net_1), parts_1) + calcul_impot_bareme(
            net_imposable_annuel(net_2), parts_2
        )
        parts_totales = parts_1 + parts_2
    else:
        nb_adultes = 2 if situation_couple == "Vie en couple" else 1
        parts_totales = calcul_parts_fiscales(nb_adultes, nb_enfants)
        impot_annuel = calcul_impot_bareme(net_imposable_annuel(revenu_net_avant_impot_total), parts_totales)

    return impot_annuel / 12, parts_totales


def charger_params():
    params = DEFAULT_PARAMS.copy()
    if not CONFIG_PATH.exists():
        return params

    try:
        with CONFIG_PATH.open("r", encoding="utf-8") as file:
            data = json.load(file)
            if isinstance(data, dict):
                params.update({k: v for k, v in data.items() if k in DEFAULT_PARAMS})
    except (OSError, json.JSONDecodeError):
        pass

    return params


def sauver_params(params):
    try:
        with CONFIG_PATH.open("w", encoding="utf-8") as file:
            json.dump(params, file, ensure_ascii=False, indent=2)
    except OSError:
        pass


def calcul_mensualite(capital, taux_annuel, duree_ans):
    if capital <= 0 or duree_ans <= 0:
        return 0.0

    n = int(duree_ans * 12)
    taux_mensuel = taux_annuel / 100 / 12

    if taux_mensuel == 0:
        return capital / n

    return capital * taux_mensuel / (1 - (1 + taux_mensuel) ** (-n))


def calcul_capacite_avec_assurance(mensualite_disponible, taux_credit, taux_assurance, duree_ans):
    """
    Calcule le capital d'emprunt maximal de sorte que :
    Mensualité crédit + Assurance = Mensualité disponible
    """
    if mensualite_disponible <= 0 or duree_ans <= 0:
        return 0.0

    n = int(duree_ans * 12)
    r = taux_credit / 100 / 12
    i = taux_assurance / 100 / 12

    if r == 0:
        coef_remboursement = (1 / n) + i
    else:
        coef_remboursement = (r / (1 - (1 + r) ** (-n))) + i

    return mensualite_disponible / coef_remboursement if coef_remboursement > 0 else 0.0


@st.cache_data
def tableau_amortissement_pret(nom_pret, capital, taux_annuel, duree_ans):
    if capital <= 0 or duree_ans <= 0:
        return pd.DataFrame(columns=["Mois", "Prêt", "Mensualité", "Capital remboursé", "Intérêts", "Capital restant dû"])

    taux_mensuel = taux_annuel / 100 / 12
    nb_mois = int(duree_ans * 12)
    mensualite = calcul_mensualite(capital, taux_annuel, duree_ans)

    crd = capital
    lignes = []

    for mois in range(1, nb_mois + 1):
        interets = crd * taux_mensuel
        remboursement_capital = mensualite - interets

        if mois == nb_mois or crd < remboursement_capital:
            remboursement_capital = crd

        crd = max(crd - remboursement_capital, 0)

        lignes.append(
            {
                "Mois": mois,
                "Prêt": nom_pret,
                "Mensualité": round(mensualite, 2),
                "Capital remboursé": round(remboursement_capital, 2),
                "Intérêts": round(interets, 2),
                "Capital restant dû": round(crd, 2),
            }
        )

    return pd.DataFrame(lignes)


def construire_amortissements(prets, assurance_mensuelle, duree_principale):
    frames = []
    for pret in prets:
        if pret["capital"] > 0:
            frames.append(
                tableau_amortissement_pret(
                    pret["nom"],
                    pret["capital"],
                    pret["taux"],
                    pret["duree"],
                )
            )

    df_detail = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()

    if df_detail.empty:
        return pd.DataFrame(columns=["Mois", "Mensualité", "Capital remboursé", "Intérêts", "Capital restant dû"]), df_detail

    df_global = (
        df_detail.groupby("Mois", as_index=False)[["Mensualité", "Capital remboursé", "Intérêts", "Capital restant dû"]]
        .sum()
        .sort_values("Mois")
    )

    if assurance_mensuelle > 0 and duree_principale > 0:
        df_global["Mensualité"] = (
            df_global["Mensualité"]
            + np.where(df_global["Mois"] <= int(duree_principale * 12), assurance_mensuelle, 0)
        ).round(2)

    return df_global, df_detail


def depense_key(name):
    return (
        name.lower()
        .replace(" ", "_")
        .replace("/", "_")
        .replace("&", "et")
        .replace("-", "_")
        .replace("é", "e")
        .replace("è", "e")
    )


def construire_depenses_sidebar(params):
    st.sidebar.header("Dépenses mensuelles")
    st.sidebar.caption("Saisie partagée avec l'onglet Reste à vivre")

    depenses_valeurs = dict(params.get("depenses_valeurs", {}))
    depenses_frequences = dict(params.get("depenses_frequences", {}))
    lignes = []

    for categorie, items in DEPENSES_TEMPLATE.items():
        with st.sidebar.expander(categorie, expanded=False):
            for nom, valeur_defaut, freq_defaut in items:
                key = depense_key(nom)
                valeur_init = float(depenses_valeurs.get(key, valeur_defaut))
                freq_init = depenses_frequences.get(key, freq_defaut)

                col1, col2 = st.columns([2, 1])
                with col1:
                    valeur = st.number_input(
                        nom,
                        min_value=0.0,
                        value=valeur_init,
                        step=10.0,
                        key=f"dep_val_{key}",
                    )
                with col2:
                    freq = st.selectbox(
                        "Fréquence",
                        ["Mensuelle", "Annuelle"],
                        index=0 if freq_init == "Mensuelle" else 1,
                        key=f"dep_freq_{key}",
                        label_visibility="collapsed",
                    )

                depenses_valeurs[key] = valeur
                depenses_frequences[key] = freq

                cout_mensuel = valeur if freq == "Mensuelle" else valeur / 12
                if cout_mensuel > 0:
                    lignes.append(
                        {
                            "Nom": nom,
                            "Catégorie": categorie,
                            "Montant Saisi": valeur,
                            "Fréquence": freq,
                            "Coût Mensuel": cout_mensuel,
                        }
                    )

    df_depenses = pd.DataFrame(lignes)
    return df_depenses, depenses_valeurs, depenses_frequences


# ---------------- CONFIGURATION PAGE ----------------
st.set_page_config(page_title="Dashboard prêt & reste à vivre", page_icon="🏠", layout="wide")
st.title("🏠 Dashboard : Simulateur de prêt & Reste à vivre")

params = charger_params()

st.sidebar.title("Paramètres")

mode_simulation = st.sidebar.radio(
    "Mode simulation",
    ["Mensualité", "Capacité d'emprunt"],
    index=0 if params["mode_simulation"] == "Mensualité" else 1,
)

st.sidebar.header("Revenus du ménage")
st.sidebar.caption("⚠️ Saisir des revenus **bruts mensuels** (avant cotisations sociales et impôt sur le revenu).")
revenu_1 = st.sidebar.number_input("Revenu 1 brut (€/mois)", min_value=0.0, value=float(params["revenu_1"]), step=100.0)
revenu_2 = st.sidebar.number_input("Revenu 2 brut (€/mois)", min_value=0.0, value=float(params["revenu_2"]), step=100.0)
autres_revenus = st.sidebar.number_input(
    "Autres revenus bruts (€/mois)",
    min_value=0.0,
    value=float(params["autres_revenus"]),
    step=50.0,
    help="Revenus fonciers, primes, etc. Si un revenu est déjà net (indépendant, foncier après charges...), ajustez le taux de charges sociales ci-dessous.",
)
taux_charges_sociales_pct = st.sidebar.number_input(
    "Taux de charges sociales salariales (%)",
    min_value=0.0,
    max_value=60.0,
    value=float(params["taux_charges_sociales_pct"]),
    step=1.0,
    help="Conversion brut → net avant impôt, utilisée pour le taux d'endettement (calculé par les banques sur le revenu net) et pour l'estimation d'impôt. ~22-25% pour un salarié du privé, ~15% fonction publique, 0% si vos revenus sont déjà nets.",
)
charges_fixes = st.sidebar.number_input(
    "Autres charges fixes hors dépenses ci-dessous (€/mois)",
    min_value=0.0,
    value=float(params["charges_fixes"]),
    step=50.0,
    help="Ex: pensions versées, crédits conso en cours non rachetés, etc."
)

revenu_total = revenu_1 + revenu_2 + autres_revenus
revenu_net_avant_impot = revenu_total * (1 - taux_charges_sociales_pct / 100)

st.sidebar.header("Foyer fiscal & composition du ménage")
situation_couple = st.sidebar.selectbox(
    "Situation",
    ["Vie en couple", "Personne seule"],
    index=0 if params["situation_couple"] == "Vie en couple" else 1,
)
nb_enfants = st.sidebar.number_input(
    "Nombre d'enfants à charge", min_value=0, max_value=10, value=int(params["nb_enfants"]), step=1
)

declaration_commune = True
enfants_rev1 = 0
enfants_rev2 = 0
if situation_couple == "Vie en couple":
    declaration_commune = st.sidebar.checkbox(
        "Déclaration fiscale commune (mariés/pacsés)",
        value=bool(params["declaration_commune"]),
        help="Décochez si vous êtes en concubinage (union libre) : chaque personne déclare alors ses impôts séparément.",
    )
    if not declaration_commune:
        enfants_rev1 = st.sidebar.number_input(
            "Dont enfants rattachés à Revenu 1",
            min_value=0,
            max_value=int(nb_enfants),
            value=int(min(params.get("enfants_rev1", 0), nb_enfants)),
            step=1,
        )
        enfants_rev2 = int(nb_enfants) - enfants_rev1

nombre_personnes_foyer = (2 if situation_couple == "Vie en couple" else 1) + nb_enfants

st.sidebar.header("Projet immobilier")
prix_bien = st.sidebar.number_input("Prix du bien (€)", min_value=0.0, value=float(params["prix_bien"]), disabled=mode_simulation == "Capacité d'emprunt")
apport = st.sidebar.number_input("Apport personnel (€)", min_value=0.0, value=float(params["apport"]))
frais_notaire_pct = st.sidebar.number_input("Frais de notaire (%)", min_value=0.0, value=float(params["frais_notaire_pct"]))
taux_credit = st.sidebar.number_input("Taux prêt principal (%)", min_value=0.0, value=float(params["taux_credit"]))
duree_principale = st.sidebar.slider("Durée prêt principal (ans)", 5, 30, int(max(5, min(30, params["duree_principale"]))))
taux_assurance = st.sidebar.number_input("Assurance prêt principal (%)", min_value=0.0, value=float(params["taux_assurance"]))
taux_endettement = st.sidebar.slider("Taux d'endettement max (%)", 20, 50, int(max(20, min(50, params["taux_endettement"]))))

st.sidebar.subheader("Prêts complémentaires (PTZ, Action Logement...)")
pret_comp_1_montant = st.sidebar.number_input("Prêt complémentaire 1 - Montant (€)", min_value=0.0, value=float(params["pret_comp_1_montant"]))
pret_comp_1_taux = st.sidebar.number_input("Prêt complémentaire 1 - Taux (%)", min_value=0.0, value=float(params["pret_comp_1_taux"]), disabled=pret_comp_1_montant <= 0)
pret_comp_1_duree = st.sidebar.slider("Prêt complémentaire 1 - Durée (ans)", 5, 30, int(max(5, min(30, params["pret_comp_1_duree"]))), disabled=pret_comp_1_montant <= 0)

pret_comp_2_montant = st.sidebar.number_input("Prêt complémentaire 2 - Montant (€)", min_value=0.0, value=float(params["pret_comp_2_montant"]))
pret_comp_2_taux = st.sidebar.number_input("Prêt complémentaire 2 - Taux (%)", min_value=0.0, value=float(params["pret_comp_2_taux"]), disabled=pret_comp_2_montant <= 0)
pret_comp_2_duree = st.sidebar.slider("Prêt complémentaire 2 - Durée (ans)", 5, 30, int(max(5, min(30, params["pret_comp_2_duree"]))), disabled=pret_comp_2_montant <= 0)

st.sidebar.subheader("Prêt relais (optionnel)")
activer_pret_relais = st.sidebar.checkbox("Activer le prêt relais", value=bool(params["activer_pret_relais"]))

if activer_pret_relais:
    prix_vente_estime = st.sidebar.number_input("Prix de vente estimé du bien actuel (€)", min_value=0.0, value=float(params["prix_vente_estime"]))
    ancien_pret_crd = st.sidebar.number_input("Capital Restant Dû sur l'ancien prêt (€)", min_value=0.0, value=float(params.get("ancien_pret_crd", 150000.0)))
    facteur_revente_banque_pct = st.sidebar.number_input("Décote banque / Quotité (%)", min_value=0.0, max_value=100.0, value=float(params["facteur_revente_banque_pct"]))
    duree_relais_mois = st.sidebar.number_input(
        "Durée estimée avant vente (mois)",
        min_value=1,
        max_value=36,
        value=int(params.get("duree_relais_mois", 6)),
        step=1,
    )
    taux_pret_relais = st.sidebar.number_input(
        "Taux du prêt relais (%/an)",
        min_value=0.0,
        value=float(params.get("taux_pret_relais", 4.0)),
        step=0.1,
        help="Le prêt relais est généralement in fine : seuls les intérêts sont payés chaque mois, le capital (l'avance) est remboursé au moment de la vente.",
    )
else:
    prix_vente_estime = float(params["prix_vente_estime"])
    ancien_pret_crd = float(params.get("ancien_pret_crd", 150000.0))
    facteur_revente_banque_pct = float(params["facteur_revente_banque_pct"])
    duree_relais_mois = int(params.get("duree_relais_mois", 6))
    taux_pret_relais = float(params.get("taux_pret_relais", 4.0))

st.sidebar.subheader("Frais annexes d'acquisition")
frais_annexes_montant = st.sidebar.number_input(
    "Frais de dossier, garantie/caution, courtage... (€)",
    min_value=0.0,
    value=float(params.get("frais_annexes_montant", 3000.0)),
    step=100.0,
    help="En plus des frais de notaire : frais de dossier bancaire, garantie (caution ou hypothèque), frais de courtage éventuels.",
)

df_depenses, depenses_valeurs, depenses_frequences = construire_depenses_sidebar(params)
total_depenses_mensuelles = df_depenses["Coût Mensuel"].sum() if not df_depenses.empty else 0.0

# ---------------- CALCULS FINANCIERS ----------------
apport_additionnel_relais = 0.0
cout_mensuel_relais = 0.0
avance_banque = 0.0
if activer_pret_relais:
    # Avance Relais = (Prix Vente * Quotité) - Capital Restant Dû
    avance_banque = prix_vente_estime * (facteur_revente_banque_pct / 100)
    apport_additionnel_relais = max(avance_banque - ancien_pret_crd, 0.0)
    # Prêt relais généralement in fine : seuls les intérêts sont dus chaque mois
    cout_mensuel_relais = avance_banque * (taux_pret_relais / 100 / 12)

apport_total = apport + apport_additionnel_relais

capital_comp_1 = max(pret_comp_1_montant, 0.0)
capital_comp_2 = max(pret_comp_2_montant, 0.0)
capital_complementaires = capital_comp_1 + capital_comp_2

mensualite_comp_1 = calcul_mensualite(capital_comp_1, pret_comp_1_taux, pret_comp_1_duree)
mensualite_comp_2 = calcul_mensualite(capital_comp_2, pret_comp_2_taux, pret_comp_2_duree)
# Le taux d'endettement bancaire (35%) se calcule sur le revenu NET avant impôt, pas sur le brut.
mensualite_max = max(revenu_net_avant_impot * (taux_endettement / 100) - charges_fixes, 0.0)

if mode_simulation == "Mensualité":
    frais_notaire = prix_bien * (frais_notaire_pct / 100)
    montant_total_a_financer = max(prix_bien + frais_notaire + frais_annexes_montant - apport_total, 0.0)
    capital_principal = max(montant_total_a_financer - capital_complementaires, 0.0)
    
    mensualite_principal = calcul_mensualite(capital_principal, taux_credit, duree_principale)
    assurance_mensuelle = capital_principal * (taux_assurance / 100) / 12
    mensualite_totale = mensualite_principal + mensualite_comp_1 + mensualite_comp_2 + assurance_mensuelle
    prix_max = prix_bien
else:
    # Calcul exact de la capacité d'emprunt en intégrant l'assurance
    mensualite_dispo_principal = max(mensualite_max - mensualite_comp_1 - mensualite_comp_2, 0.0)
    capital_principal = calcul_capacite_avec_assurance(
        mensualite_dispo_principal, taux_credit, taux_assurance, duree_principale
    )
    
    assurance_mensuelle = capital_principal * (taux_assurance / 100) / 12
    mensualite_principal = calcul_mensualite(capital_principal, taux_credit, duree_principale)
    mensualite_totale = mensualite_principal + mensualite_comp_1 + mensualite_comp_2 + assurance_mensuelle
    
    frais_factor = 1 + (frais_notaire_pct / 100)
    prix_max = (
        max(capital_principal + capital_complementaires + apport_total - frais_annexes_montant, 0.0) / frais_factor
        if frais_factor > 0
        else 0.0
    )
    frais_notaire = prix_max * (frais_notaire_pct / 100)

prets = [
    {"nom": "Prêt principal", "capital": capital_principal, "taux": taux_credit, "duree": duree_principale},
    {"nom": "Prêt complémentaire 1", "capital": capital_comp_1, "taux": pret_comp_1_taux, "duree": pret_comp_1_duree},
    {"nom": "Prêt complémentaire 2", "capital": capital_comp_2, "taux": pret_comp_2_taux, "duree": pret_comp_2_duree},
]

df_amort, df_amort_detail = construire_amortissements(prets, assurance_mensuelle, duree_principale)

# ---------------- FISCALITÉ (estimation) ----------------
impot_mensuel_estime, parts_fiscales = estimer_impot_mensuel(
    revenu_net_avant_impot,
    situation_couple,
    declaration_commune,
    nb_enfants,
    enfants_rev1,
    enfants_rev2,
    revenu_1,
    revenu_2,
    autres_revenus,
    taux_charges_sociales_pct,
)
cotisations_sociales_mensuelles = revenu_total - revenu_net_avant_impot

# Reste à vivre net d'impôt, après remboursement du prêt, avant charges fixes et dépenses courantes
reste_a_vivre_brut = revenu_net_avant_impot - impot_mensuel_estime - mensualite_totale
# Reste à vivre "façon banque" : après charges fixes récurrentes, avant dépenses courantes discrétionnaires
reste_a_vivre_avant_depenses_courantes = reste_a_vivre_brut - charges_fixes
reste_a_vivre_par_personne = (
    reste_a_vivre_avant_depenses_courantes / nombre_personnes_foyer if nombre_personnes_foyer > 0 else reste_a_vivre_avant_depenses_courantes
)
epargne_disponible = reste_a_vivre_avant_depenses_courantes - total_depenses_mensuelles

# Sauvegarde d'état
sauver_params(
    {
        "mode_simulation": mode_simulation,
        "revenu_1": revenu_1,
        "revenu_2": revenu_2,
        "autres_revenus": autres_revenus,
        "charges_fixes": charges_fixes,
        "prix_bien": prix_bien,
        "apport": apport,
        "frais_notaire_pct": frais_notaire_pct,
        "taux_credit": taux_credit,
        "duree_principale": duree_principale,
        "taux_assurance": taux_assurance,
        "taux_endettement": taux_endettement,
        "pret_comp_1_montant": pret_comp_1_montant,
        "pret_comp_1_taux": pret_comp_1_taux,
        "pret_comp_1_duree": pret_comp_1_duree,
        "pret_comp_2_montant": pret_comp_2_montant,
        "pret_comp_2_taux": pret_comp_2_taux,
        "pret_comp_2_duree": pret_comp_2_duree,
        "activer_pret_relais": activer_pret_relais,
        "ancien_pret_crd": ancien_pret_crd,
        "prix_vente_estime": prix_vente_estime,
        "facteur_revente_banque_pct": facteur_revente_banque_pct,
        "duree_relais_mois": duree_relais_mois,
        "taux_pret_relais": taux_pret_relais,
        "frais_annexes_montant": frais_annexes_montant,
        "taux_charges_sociales_pct": taux_charges_sociales_pct,
        "situation_couple": situation_couple,
        "declaration_commune": declaration_commune,
        "nb_enfants": nb_enfants,
        "enfants_rev1": enfants_rev1,
        "depenses_valeurs": depenses_valeurs,
        "depenses_frequences": depenses_frequences,
    }
)

# ---------------- INTERFACE COMPOSANTS ----------------
onglet_pret, onglet_rav = st.tabs(["📈 Simulateur de prêt", "💶 Reste à vivre & Budget"])

with onglet_pret:
    col1, col2, col3 = st.columns(3)
    col1.metric("Capital prêt principal", f"{capital_principal:,.0f} €")
    col2.metric("Mensualité totale (avec assurance)", f"{mensualite_totale:,.0f} €/mois")
    
    if mode_simulation == "Mensualité":
        col3.metric("Reste à vivre (net avant impôt, hors dépenses détaillées)", f"{(revenu_net_avant_impot - charges_fixes - mensualite_totale):,.0f} €/mois")
    else:
        col3.metric("Prix d'achat estimé max", f"{prix_max:,.0f} €")

    st.caption(
        f"Apport perso: {apport:,.0f} € | Net Relais disponible: {apport_additionnel_relais:,.0f} € | Apport Total: {apport_total:,.0f} € | "
        f"Frais de notaire: {frais_notaire:,.0f} € | Frais annexes (dossier/garantie...): {frais_annexes_montant:,.0f} €"
    )

    if mode_simulation == "Capacité d'emprunt":
        st.caption(
            f"Mensualité max autorisée ({taux_endettement}% du revenu **net**): {mensualite_max:,.0f} €/mois | Mensualité totale réelle: {mensualite_totale:,.0f} €/mois"
        )

    if activer_pret_relais:
        st.info(
            f"💡 Prêt relais : coût mensuel estimé (intérêts intercalaires sur {avance_banque:,.0f} € d'avance) "
            f"≈ **{cout_mensuel_relais:,.0f} €/mois** pendant environ {duree_relais_mois} mois, jusqu'à la vente de l'ancien bien. "
            f"Ce montant n'est **pas** inclus dans la mensualité totale ci-dessus (prêt in fine, capital remboursé à la vente) — "
            f"voir son impact sur le reste à vivre dans l'onglet dédié."
        )

    st.subheader("Tableau d'amortissement agrégé")
    
    col_df, col_exp = st.columns([4, 1])
    with col_exp:
        if not df_amort.empty:
            csv = df_amort.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="📥 Télécharger (.CSV)",
                data=csv,
                file_name="tableau_amortissement.csv",
                mime="text/csv",
            )

    st.dataframe(df_amort, use_container_width=True, height=350)

    if not df_amort.empty:
        fig_crd = px.line(df_amort, x="Mois", y="Capital restant dû", title="Évolution du capital restant dû total")
        st.plotly_chart(fig_crd, use_container_width=True)

    if not df_amort_detail.empty and len(df_amort_detail["Prêt"].unique()) > 1:
        st.subheader("Répartition du capital par prêt")
        pivot_detail = df_amort_detail.pivot_table(index="Mois", columns="Prêt", values="Capital restant dû", aggfunc="sum").reset_index()
        fig_area = px.area(
            pivot_detail,
            x="Mois",
            y=[c for c in pivot_detail.columns if c != "Mois"],
            title="Capital restant dû ventilé par prêt",
        )
        st.plotly_chart(fig_area, use_container_width=True)

with onglet_rav:
    # Endettement calculé sur le revenu NET avant impôt (base utilisée par les banques), charges fixes incluses
    taux_endettement_reel = (
        ((mensualite_totale + charges_fixes) / revenu_net_avant_impot * 100) if revenu_net_avant_impot > 0 else 0
    )

    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric("Revenus bruts", f"{revenu_total:,.0f} €/mois", help="Revenu net avant impôt estimé : "
              f"{revenu_net_avant_impot:,.0f} €/mois")
    k2.metric("Mensualité prêt", f"{mensualite_totale:,.0f} €/mois", delta=f"Endettement: {taux_endettement_reel:.1f}%", delta_color="inverse" if taux_endettement_reel > 35 else "normal")
    k3.metric("Dépenses courantes", f"{total_depenses_mensuelles:,.0f} €/mois")
    k4.metric("Reste à vivre brut (net d'impôt)", f"{reste_a_vivre_brut:,.0f} €/mois")
    k5.metric("Capacité d'épargne nette", f"{epargne_disponible:,.0f} €/mois")

    if taux_endettement_reel > 35:
        st.warning(f"⚠️ Taux d'endettement supérieur aux recommendations usuellement admises (35%) : {taux_endettement_reel:.1f}%")
    if epargne_disponible < 0:
        st.error(f"🚨 Déficit budgétaire : Épargne nette négative de {abs(epargne_disponible):,.0f} €/mois")

    st.subheader("Fiscalité & composition du foyer")
    f1, f2, f3, f4 = st.columns(4)
    f1.metric("Parts fiscales", f"{parts_fiscales:.2f}")
    f2.metric("Personnes au foyer", f"{nombre_personnes_foyer}")
    f3.metric("Impôt sur le revenu estimé", f"{impot_mensuel_estime:,.0f} €/mois")
    f4.metric("Cotisations sociales estimées", f"{cotisations_sociales_mensuelles:,.0f} €/mois")
    st.caption(
        "⚠️ Estimation simplifiée du barème 2026 (revenus 2025), quotient familial hors décote, réductions/crédits "
        "d'impôt et majoration 'parent isolé'. Ne remplace pas le simulateur officiel impots.gouv.fr."
    )

    st.subheader("Reste à vivre par personne")
    with st.expander("ℹ️ Seuils indicatifs (ajustables — variables selon les banques)"):
        seuil_1ere_personne = st.number_input("Seuil 1ère personne (€/mois)", min_value=0.0, value=800.0, step=50.0)
        seuil_personne_supp = st.number_input("Seuil par personne supplémentaire (€/mois)", min_value=0.0, value=400.0, step=50.0)
    seuil_foyer = seuil_1ere_personne + seuil_personne_supp * max(nombre_personnes_foyer - 1, 0)

    p1, p2 = st.columns(2)
    p1.metric(
        "Reste à vivre par personne",
        f"{reste_a_vivre_par_personne:,.0f} €/mois",
        help="Revenu net avant impôt - impôt estimé - mensualité - charges fixes, divisé par le nombre de personnes du foyer. Hors dépenses courantes discrétionnaires (alimentation, loisirs...).",
    )
    p2.metric("Seuil indicatif du foyer", f"{seuil_foyer:,.0f} €/mois")
    if reste_a_vivre_avant_depenses_courantes < seuil_foyer:
        st.warning(
            f"⚠️ Le reste à vivre du foyer ({reste_a_vivre_avant_depenses_courantes:,.0f} €/mois) est inférieur au seuil "
            f"indicatif ({seuil_foyer:,.0f} €/mois pour {nombre_personnes_foyer} personne(s)). Certaines banques pourraient refuser le dossier à ce niveau."
        )

    if activer_pret_relais:
        rav_pendant_relais = epargne_disponible - cout_mensuel_relais
        st.info(
            f"💡 Pendant la période de relais (≈{duree_relais_mois} mois), le coût du prêt relais "
            f"({cout_mensuel_relais:,.0f} €/mois) réduit temporairement la capacité d'épargne à "
            f"**{rav_pendant_relais:,.0f} €/mois**."
        )

    c1, c2 = st.columns(2)

    with c1:
        repartition = pd.DataFrame(
            {
                "Poste": ["Cotisations sociales", "Impôt sur le revenu", "Prêt immobilier", "Charges fixes", "Dépenses courantes", "Épargne nette"],
                "Montant": [
                    max(cotisations_sociales_mensuelles, 0),
                    max(impot_mensuel_estime, 0),
                    mensualite_totale,
                    charges_fixes,
                    total_depenses_mensuelles,
                    max(epargne_disponible, 0),
                ],
            }
        )
        fig_global = px.pie(repartition, values="Montant", names="Poste", hole=0.45, title="Répartition du revenu brut")
        st.plotly_chart(fig_global, use_container_width=True)

    with c2:
        if not df_depenses.empty:
            df_cat = df_depenses.groupby("Catégorie", as_index=False)["Coût Mensuel"].sum()
            fig_cat = px.pie(df_cat, values="Coût Mensuel", names="Catégorie", hole=0.35, title="Dépenses par catégorie")
            st.plotly_chart(fig_cat, use_container_width=True)
        else:
            st.info("Aucune dépense courante renseignée dans la barre latérale.")

    st.subheader("Flux financier mensuel (Waterfall)")
    waterfall_x = ["Revenus bruts", "Cotisations sociales", "Impôt sur le revenu", "Prêt Immo", "Charges fixes"]
    waterfall_y = [revenu_total, -cotisations_sociales_mensuelles, -impot_mensuel_estime, -mensualite_totale, -charges_fixes]
    waterfall_measure = ["absolute", "relative", "relative", "relative", "relative"]

    if not df_depenses.empty:
        df_cat = df_depenses.groupby("Catégorie", as_index=False)["Coût Mensuel"].sum()
        for _, row in df_cat.iterrows():
            waterfall_x.append(row["Catégorie"])
            waterfall_y.append(-row["Coût Mensuel"])
            waterfall_measure.append("relative")

    waterfall_x.append("Épargne nette")
    waterfall_y.append(epargne_disponible)
    waterfall_measure.append("total")

    fig_waterfall = go.Figure(
        go.Waterfall(
            x=waterfall_x,
            y=waterfall_y,
            measure=waterfall_measure,
            text=[f"{v:+,.0f} €" if m != "total" else f"{v:,.0f} €" for v, m in zip(waterfall_y, waterfall_measure)],
            decreasing={"marker": {"color": "#E63946"}},
            increasing={"marker": {"color": "#2A9D8F"}},
            totals={"marker": {"color": "#1D3557"}},
        )
    )
    fig_waterfall.update_layout(showlegend=False)
    st.plotly_chart(fig_waterfall, use_container_width=True)

    st.subheader("Détail des dépenses courantes")
    if not df_depenses.empty:
        st.dataframe(df_depenses.sort_values("Coût Mensuel", ascending=False), use_container_width=True)
    else:
        st.info("Aucune dépense courante renseignée.")