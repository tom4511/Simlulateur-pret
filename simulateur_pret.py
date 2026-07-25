
import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import json
from pathlib import Path



#Commande:
#streamlit run Correlation\REM\simulateur_emprunt_v2.py


BRUT_NET = 0.77 # pour passer du salaire brut au salaire net
CONFIG_PATH = Path(__file__).with_name("simulateur_pret_config.json")

DEFAULT_PARAMS = {
    "mode_simulation": "Mensualité",
    "prix_bien": 300000,
    "apport": 30000,
    "frais_notaire_pct": 8.0,
    "taux_credit": 3.5,
    "pret_comp_1_montant": 0,
    "pret_comp_1_taux": 1.0,
    "pret_comp_1_duree": 10,
    "pret_comp_2_montant": 0,
    "pret_comp_2_taux": 1.0,
    "pret_comp_2_duree": 10,
    "taux_assurance": 0.34,
    "duree": 25,
    "mode_revenus": "Revenus mensuels",
    "revenus": 4500,
    "revenus_annuels_brut": 60000,
    "charges": 0,
    "taux_endettement": 35,
    "activer_pret_relais": False,
    "ancien_pret_total_emprunte": 200000,
    "ancien_pret_deja_rembourse": 50000,
    "prix_vente_estime": 300000,
    "facteur_revente_banque_pct": 70.0,
}

st.set_page_config(
    page_title="Simulateur de prêt immobilier",
    layout="wide"
)


# -----------------------------
# Fonctions
# -----------------------------

def calcul_mensualite(capital, taux_annuel, duree):
    if capital <= 0 or duree <= 0:
        return 0

    taux_mensuel = taux_annuel / 100 / 12
    n = duree * 12

    if taux_mensuel == 0:
        return capital / n

    return capital * taux_mensuel / (
        1 - (1 + taux_mensuel) ** (-n)
    )


def calcul_capacite(mensualite, taux_annuel, duree):
    if mensualite <= 0 or duree <= 0:
        return 0

    taux_mensuel = taux_annuel / 100 / 12
    n = duree * 12

    if taux_mensuel == 0:
        return mensualite * n

    return mensualite * (
        (1 - (1 + taux_mensuel) ** (-n))
        / taux_mensuel
    )

def impot_revenu_france(brut_annuel, nb_parts=1):
    """
    Estimation de l'impôt sur le revenu français.

    Paramètres :
        brut_annuel (float) : salaire brut annuel du contrat
        nb_parts (float)    : nombre de parts fiscales

    Retour :
        dict contenant :
            - brut_annuel
            - net_imposable_estime
            - nb_parts
            - impot
            - taux_effectif
    """

    # Approximation salarié du privé
    net_imposable = brut_annuel * BRUT_NET

    revenu_par_part = net_imposable / nb_parts

    tranches = [
        (11497, 0.00),
        (29315, 0.11),
        (83823, 0.30),
        (180294, 0.41),
        (float("inf"), 0.45)
    ]

    impot_par_part = 0
    bas = 0

    for haut, taux in tranches:
        if revenu_par_part <= bas:
            break

        montant = min(revenu_par_part, haut) - bas
        impot_par_part += montant * taux
        bas = haut

    impot_total = impot_par_part * nb_parts

    return {
        "brut_annuel": round(brut_annuel, 2),
        "net_imposable_estime": round(net_imposable, 2),
        "nb_parts": nb_parts,
        "impot": round(impot_total, 2),
        "taux_effectif": round(100 * impot_total / brut_annuel, 2)
    }

def calcul_salaire_mensuel(brut_annuel):
    net_imposable = brut_annuel * BRUT_NET
    # Calcul du salaire mensuel net
    salaire_mensuel = net_imposable / 12

    return salaire_mensuel

def tableau_amortissement_pret(
    nom_pret,
    capital,
    taux_annuel,
    duree
):
    if capital <= 0:
        return pd.DataFrame(columns=[
            "Mois",
            "Prêt",
            "Mensualité",
            "Capital remboursé",
            "Intérêts",
            "Capital restant dû"
        ])

    taux_mensuel = taux_annuel / 100 / 12
    nb_mois = duree * 12

    mensualite = calcul_mensualite(
        capital,
        taux_annuel,
        duree
    )

    crd = capital

    lignes = []

    for mois in range(1, nb_mois + 1):

        interets = crd * taux_mensuel

        remboursement_capital = (
            mensualite - interets
        )

        if mois == nb_mois:
            remboursement_capital = crd

        crd -= remboursement_capital

        if crd < 0:
            crd = 0

        lignes.append({
            "Prêt": nom_pret,
            "Mois": mois,
            "Mensualité": round(
                mensualite,
                2
            ),
            "Capital remboursé": round(
                remboursement_capital,
                2
            ),
            "Intérêts": round(
                interets,
                2
            ),
            "Capital restant dû": round(
                crd,
                2
            )
        })

    return pd.DataFrame(lignes)


def construire_tableaux_amortissement(
    prets,
    assurance_mensuelle=0,
    duree_assurance=0
):
    details = []

    for pret in prets:
        details.append(
            tableau_amortissement_pret(
                pret["nom"],
                pret["capital"],
                pret["taux"],
                pret["duree"]
            )
        )

    df_detail = pd.concat(details, ignore_index=True)

    df_global = df_detail.groupby(
        "Mois",
        as_index=False
    )[[
        "Mensualité",
        "Capital remboursé",
        "Intérêts",
        "Capital restant dû"
    ]].sum()

    if not df_global.empty and assurance_mensuelle > 0 and duree_assurance > 0:
        df_global["Assurance"] = np.where(
            df_global["Mois"] <= duree_assurance * 12,
            assurance_mensuelle,
            0
        )
        df_global["Mensualité"] = (
            df_global["Mensualité"]
            + df_global["Assurance"]
        ).round(2)
        df_global = df_global.drop(columns=["Assurance"])

    return df_global, df_detail


def charger_params():
    params = DEFAULT_PARAMS.copy()

    if not CONFIG_PATH.exists():
        return params

    try:
        with CONFIG_PATH.open("r", encoding="utf-8") as file:
            data = json.load(file)
    except (OSError, json.JSONDecodeError):
        return params

    if not isinstance(data, dict):
        return params

    for key in params:
        if key in data:
            params[key] = data[key]

    return params


def sauver_params(params):
    try:
        with CONFIG_PATH.open("w", encoding="utf-8") as file:
            json.dump(params, file, ensure_ascii=False, indent=2)
    except OSError:
        pass


# -----------------------------
# Sidebar
# -----------------------------

st.sidebar.title("Paramètres")

params = charger_params()

options_mode_simulation = ["Mensualité", "Capacité d'emprunt"]
if params["mode_simulation"] not in options_mode_simulation:
    params["mode_simulation"] = DEFAULT_PARAMS["mode_simulation"]

options_mode_revenus = ["Revenus mensuels", "Salaire annuel brut"]
if params["mode_revenus"] not in options_mode_revenus:
    params["mode_revenus"] = DEFAULT_PARAMS["mode_revenus"]

duree_value = int(params["duree"])
duree_value = max(5, min(30, duree_value))

taux_endettement_value = int(params["taux_endettement"])
taux_endettement_value = max(20, min(50, taux_endettement_value))

mode_simulation = st.sidebar.radio(
    "Mode de simulation",
    options_mode_simulation,
    index=options_mode_simulation.index(params["mode_simulation"])
)

prix_bien = st.sidebar.number_input(
    "Prix du bien (€)",
    value=float(params["prix_bien"]),
    disabled=mode_simulation == "Mensualité"
)

apport = st.sidebar.number_input(
    "Apport (€)",
    value=float(params["apport"])
)

frais_notaire_pct = st.sidebar.number_input(
    "Frais de notaire (%)",
    value=float(params["frais_notaire_pct"])
)

taux_credit = st.sidebar.number_input(
    "Taux crédit (%)",
    value=float(params["taux_credit"])
)

duree = st.sidebar.slider(
    "Durée prêt principal (ans)",
    5,
    30,
    duree_value
)

st.sidebar.subheader("Prêts complémentaires")

pret_comp_1_montant = st.sidebar.number_input(
    "Prêt complémentaire 1 - Montant (€)",
    min_value=0.0,
    value=float(params["pret_comp_1_montant"])
)

pret_comp_1_taux = st.sidebar.number_input(
    "Prêt complémentaire 1 - Taux (%)",
    min_value=0.0,
    value=float(params["pret_comp_1_taux"]),
    disabled=pret_comp_1_montant <= 0
)

pret_comp_1_duree_value = int(params.get("pret_comp_1_duree", 10))
pret_comp_1_duree_value = max(5, min(30, pret_comp_1_duree_value))

pret_comp_1_duree = st.sidebar.slider(
    "Prêt complémentaire 1 - Durée (ans)",
    5,
    30,
    pret_comp_1_duree_value,
    disabled=pret_comp_1_montant <= 0
)

pret_comp_2_montant = st.sidebar.number_input(
    "Prêt complémentaire 2 - Montant (€)",
    min_value=0.0,
    value=float(params["pret_comp_2_montant"])
)

pret_comp_2_taux = st.sidebar.number_input(
    "Prêt complémentaire 2 - Taux (%)",
    min_value=0.0,
    value=float(params["pret_comp_2_taux"]),
    disabled=pret_comp_2_montant <= 0
)

pret_comp_2_duree_value = int(params.get("pret_comp_2_duree", 10))
pret_comp_2_duree_value = max(5, min(30, pret_comp_2_duree_value))

pret_comp_2_duree = st.sidebar.slider(
    "Prêt complémentaire 2 - Durée (ans)",
    5,
    30,
    pret_comp_2_duree_value,
    disabled=pret_comp_2_montant <= 0
)

taux_assurance = st.sidebar.number_input(
    "Assurance (%)",
    value=float(params["taux_assurance"])
)

mode_revenus = st.sidebar.radio(
    "Mode de revenus",
    options_mode_revenus,
    index=options_mode_revenus.index(params["mode_revenus"])
)

revenus = st.sidebar.number_input(
    "Revenus mensuels (€)",
    value=float(params["revenus"]),
    disabled=mode_revenus == "Salaire annuel brut"
)

revenus_annuels_brut = st.sidebar.number_input(
    "Salaire annuel brut (€)",
    value=float(params["revenus_annuels_brut"]),
    disabled=mode_revenus == "Revenus mensuels"
)

charges = st.sidebar.number_input(
    "Charges mensuelles (€)",
    value=float(params["charges"])
)

taux_endettement = st.sidebar.slider(
    "Taux d'endettement (%)",
    20,
    50,
    taux_endettement_value,
    disabled=mode_simulation == "Capacité d'emprunt"
)

st.sidebar.subheader("Prêt relais")

activer_pret_relais = st.sidebar.checkbox(
    "Activer le prêt relais",
    value=bool(params.get("activer_pret_relais", False))
)

if activer_pret_relais:
    ancien_pret_total_emprunte = st.sidebar.number_input(
        "Ancien prêt - Total emprunté (€)",
        min_value=0.0,
        value=float(params.get("ancien_pret_total_emprunte", 200000.0))
    )

    ancien_pret_deja_rembourse = st.sidebar.number_input(
        "Ancien prêt - Déjà remboursé (€)",
        min_value=0.0,
        value=float(params.get("ancien_pret_deja_rembourse", 50000.0))
    )

    prix_vente_estime = st.sidebar.number_input(
        "Prix de vente estimé (€)",
        min_value=0.0,
        value=float(params.get("prix_vente_estime", 300000.0))
    )

    facteur_revente_banque_pct = st.sidebar.number_input(
        "Facteur de revente banque (%)",
        min_value=0.0,
        max_value=100.0,
        value=float(params.get("facteur_revente_banque_pct", 70.0))
    )
else:
    ancien_pret_total_emprunte = float(params.get("ancien_pret_total_emprunte", 200000.0))
    ancien_pret_deja_rembourse = float(params.get("ancien_pret_deja_rembourse", 50000.0))
    prix_vente_estime = float(params.get("prix_vente_estime", 300000.0))
    facteur_revente_banque_pct = float(params.get("facteur_revente_banque_pct", 70.0))

sauver_params({
    "mode_simulation": mode_simulation,
    "prix_bien": prix_bien,
    "apport": apport,
    "frais_notaire_pct": frais_notaire_pct,
    "taux_credit": taux_credit,
    "pret_comp_1_montant": pret_comp_1_montant,
    "pret_comp_1_taux": pret_comp_1_taux,
    "pret_comp_1_duree": pret_comp_1_duree,
    "pret_comp_2_montant": pret_comp_2_montant,
    "pret_comp_2_taux": pret_comp_2_taux,
    "pret_comp_2_duree": pret_comp_2_duree,
    "taux_assurance": taux_assurance,
    "duree": duree,
    "mode_revenus": mode_revenus,
    "revenus": revenus,
    "revenus_annuels_brut": revenus_annuels_brut,
    "charges": charges,
    "taux_endettement": taux_endettement,
    "activer_pret_relais": activer_pret_relais,
    "ancien_pret_total_emprunte": ancien_pret_total_emprunte,
    "ancien_pret_deja_rembourse": ancien_pret_deja_rembourse,
    "prix_vente_estime": prix_vente_estime,
    "facteur_revente_banque_pct": facteur_revente_banque_pct,
})

# -----------------------------
# Calculs
# -----------------------------

frais_notaire = prix_bien * frais_notaire_pct / 100

apport_additionnel_relais = 0
if activer_pret_relais:
    apport_additionnel_relais = (
        prix_vente_estime * (facteur_revente_banque_pct / 100)
        + ancien_pret_deja_rembourse
        - ancien_pret_total_emprunte
    )

apport_total = apport + apport_additionnel_relais

montant_total_a_financer = max(
    prix_bien
    + frais_notaire
    - apport_total,
    0
)

capital_pret_comp_1 = max(pret_comp_1_montant, 0)
capital_pret_comp_2 = max(pret_comp_2_montant, 0)
capital_prets_complementaires = (
    capital_pret_comp_1
    + capital_pret_comp_2
)

capital = 0
assurance_mensuelle = 0
mensualite_pret_comp_1 = 0
mensualite_pret_comp_2 = 0

st.title("🏠 Simulateur Immobilier")

if mode_simulation == "Capacité d'emprunt":

    if mode_revenus == "Salaire annuel brut":
        revenus_mensuels = calcul_salaire_mensuel(revenus_annuels_brut)
    else:
        revenus_mensuels = revenus

    capital = max(
        montant_total_a_financer - capital_prets_complementaires,
        0
    )

    mensualite_pret_comp_1 = calcul_mensualite(
        capital_pret_comp_1,
        pret_comp_1_taux,
        pret_comp_1_duree
    )

    mensualite_pret_comp_2 = calcul_mensualite(
        capital_pret_comp_2,
        pret_comp_2_taux,
        pret_comp_2_duree
    )

    assurance_mensuelle = (
        capital
        * (taux_assurance / 100)
        / 12
    )

    mensualite_credit = calcul_mensualite(
        capital,
        taux_credit,
        duree
    )

    mensualite_totale = (
        mensualite_credit
        + mensualite_pret_comp_1
        + mensualite_pret_comp_2
        + assurance_mensuelle
    )

    reste_a_vivre = (
        revenus_mensuels
        - charges
        - mensualite_totale
    )

    col1, col2, col3 = st.columns(3)

    col1.metric(
        "Capital total emprunté",
        f"{(capital + capital_prets_complementaires):,.0f} €"
    )

    col2.metric(
        "Mensualité",
        f"{mensualite_totale:,.0f} €"
    )

    col3.metric(
        "Reste à vivre",
        f"{reste_a_vivre:,.0f} €"
    )

    st.caption(
        f"Prêt principal: {capital:,.0f} € à {taux_credit:.2f}% sur {duree} ans | "
        f"Complémentaire 1: {capital_pret_comp_1:,.0f} € à {pret_comp_1_taux:.2f}% sur {pret_comp_1_duree} ans | "
        f"Complémentaire 2: {capital_pret_comp_2:,.0f} € à {pret_comp_2_taux:.2f}% sur {pret_comp_2_duree} ans"
    )

else:
    if mode_revenus == "Salaire annuel brut":
        revenus_mensuels = calcul_salaire_mensuel(revenus_annuels_brut)
    else:
        revenus_mensuels = revenus

    mensualite_pret_comp_1 = calcul_mensualite(
        capital_pret_comp_1,
        pret_comp_1_taux,
        pret_comp_1_duree
    )

    mensualite_pret_comp_2 = calcul_mensualite(
        capital_pret_comp_2,
        pret_comp_2_taux,
        pret_comp_2_duree
    )

    mensualite_max = (
        revenus_mensuels
        * taux_endettement
        / 100
    ) - charges

    mensualite_disponible_principal = max(
        mensualite_max
        - mensualite_pret_comp_1
        - mensualite_pret_comp_2,
        0
    )

    capital = calcul_capacite(
        mensualite_disponible_principal,
        taux_credit,
        duree
    )

    assurance_mensuelle = (
        capital
        * (taux_assurance / 100)
        / 12
    )

    prix_max = (
        capital
        + capital_prets_complementaires
        + apport_total
    ) / (1 + frais_notaire_pct / 100)

    col1, col2, col3 = st.columns(3)

    col1.metric(
        "Mensualité max",
        f"{mensualite_max:,.0f} €"
    )

    col2.metric(
        "Capacité prêt principal",
        f"{capital:,.0f} €"
    )

    col3.metric(
        "Prix d'achat possible",
        f"{prix_max:,.0f} €"
    )

    st.caption(
        f"Mensualité absorbée par prêts complémentaires: "
        f"{(mensualite_pret_comp_1 + mensualite_pret_comp_2):,.0f} € / mois"
    )

if activer_pret_relais:
    st.caption(
        f"Apport additionnel prêt relais: {apport_additionnel_relais:,.0f} € "
        f"(apport total utilisé: {apport_total:,.0f} €)"
    )

prets = [
    {
        "nom": "Prêt principal",
        "capital": capital,
        "taux": taux_credit,
        "duree": duree,
    },
    {
        "nom": "Prêt complémentaire 1",
        "capital": capital_pret_comp_1,
        "taux": pret_comp_1_taux,
        "duree": pret_comp_1_duree,
    },
    {
        "nom": "Prêt complémentaire 2",
        "capital": capital_pret_comp_2,
        "taux": pret_comp_2_taux,
        "duree": pret_comp_2_duree,
    },
]

# -----------------------------
# Tableau d'amortissement
# -----------------------------

st.header("📋 Tableau d'amortissement")

df, df_detail = construire_tableaux_amortissement(
    prets,
    assurance_mensuelle,
    duree
)

st.dataframe(
    df,
    use_container_width=True,
    height=500
)

# -----------------------------
# Capital restant dû
# -----------------------------

st.header("📈 Évolution du capital restant dû")

fig_crd = px.line(
    df,
    x="Mois",
    y="Capital restant dû"
)

st.plotly_chart(
    fig_crd,
    use_container_width=True
)

# -----------------------------
# Détail par prêt
# -----------------------------

st.header("🧩 Détail des prêts")

if df_detail.empty:
    st.info("Aucun prêt actif à détailler.")
else:
    df_mensualite_par_pret = df_detail.groupby(
        "Prêt",
        as_index=False
    )["Mensualité"].sum()

    if assurance_mensuelle > 0:
        df_mensualite_par_pret = pd.concat(
            [
                df_mensualite_par_pret,
                pd.DataFrame({
                    "Prêt": ["Assurance"],
                    "Mensualité": [assurance_mensuelle * duree * 12]
                })
            ],
            ignore_index=True
        )

    fig_repartition_mensualite = px.pie(
        df_mensualite_par_pret,
        names="Prêt",
        values="Mensualité",
        title="Part de chaque prêt dans le total remboursé"
    )

    st.plotly_chart(
        fig_repartition_mensualite,
        use_container_width=True
    )

    df_crd_par_pret = df_detail.pivot_table(
        index="Mois",
        columns="Prêt",
        values="Capital restant dû",
        aggfunc="sum"
    ).reset_index()

    colonnes_prets = [
        col for col in df_crd_par_pret.columns
        if col != "Mois"
    ]

    if colonnes_prets:
        fig_crd_par_pret = px.area(
            df_crd_par_pret,
            x="Mois",
            y=colonnes_prets,
            title="Évolution du capital restant dû par prêt"
        )

        st.plotly_chart(
            fig_crd_par_pret,
            use_container_width=True
        )

# -----------------------------
# Capital vs intérêts
# -----------------------------

st.header("💰 Répartition Capital / Intérêts")

capital_total = df["Capital remboursé"].sum()
interets_total = df["Intérêts"].sum()

df_repartition = pd.DataFrame({
    "Type": ["Capital", "Intérêts"],
    "Montant": [
        capital_total,
        interets_total
    ]
})

fig_pie = px.pie(
    df_repartition,
    names="Type",
    values="Montant"
)

st.plotly_chart(
    fig_pie,
    use_container_width=True
)

# -----------------------------
# Statistiques
# -----------------------------

st.header("📊 Synthèse")

cout_credit = (
    df["Intérêts"].sum()
)

cout_assurance = (
    assurance_mensuelle
    * duree
    * 12
)

st.write(
    f"**Coût total des intérêts :** {cout_credit:,.0f} €"
)

st.write(
    f"**Coût total de l'assurance :** {cout_assurance:,.0f} €"
)

st.write(
    f"**Coût global du financement :** {(cout_credit + cout_assurance):,.0f} €"
)

