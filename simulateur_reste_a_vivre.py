import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

# Configuration de la page
st.set_page_config(
    page_title="Simulateur de Reste à Vivre & Prêt Immo",
    page_icon="🏠",
    layout="wide"
)

st.title("🏠 Simulateur de Prêt Immobilier & Reste à Vivre")
st.markdown("Analysez précisément la décomposition de vos dépenses mensuelles et votre capacité d'épargne après projet immobilier.")

# ---------------------------------------------------------
# SIDEBAR : Saisie des données
# ---------------------------------------------------------
st.sidebar.header("💶 1. Revenus du Ménage")
rev_1 = st.sidebar.number_input("Salaire / Revenu 1 (€/mois)", min_value=0, value=3000, step=100)
rev_2 = st.sidebar.number_input("Salaire / Revenu 2 (€/mois)", min_value=0, value=2000, step=100)
autres_rev = st.sidebar.number_input("Autres revenus (€/mois)", min_value=0, value=0, step=50)

revenu_total = rev_1 + rev_2 + autres_rev

st.sidebar.header("🔑 2. Prêt Immobilier")
mensualite_immo = st.sidebar.number_input("Mensualité du prêt (€/mois)", min_value=0, value=1400, step=50)
assurance_immo = st.sidebar.number_input("Assurance prêt (€/mois)", min_value=0, value=60, step=10)

pret_total = mensualite_immo + assurance_immo

st.sidebar.header("📋 3. Dépenses Courantes")
st.sidebar.caption("Indiquez le montant et la fréquence (Mensuelle / Annuelle)")

# Structure des catégories de dépenses prédéfinies
categories_def = {
    "Logement & Énergies": [
        ("Taxe foncière", 1800, "Annuelle"),
        ("Électricité & Gaz", 120, "Mensuelle"),
        ("Eau", 35, "Mensuelle"),
        ("Charges de copropriété", 150, "Mensuelle"),
        ("Entretien & petits travaux", 50, "Mensuelle")
    ],
    "Vie quotidienne & Alimentation": [
        ("Courses alimentaires", 550, "Mensuelle"),
        ("Restos, livraisons & sorties", 200, "Mensuelle"),
        ("Hygiène, pharmacie & entretien", 80, "Mensuelle"),
        ("Animaux de compagnie", 40, "Mensuelle")
    ],
    "Transports": [
        ("Carburant / Recharge EV", 150, "Mensuelle"),
        ("Assurance auto / moto", 720, "Annuelle"),
        ("Transports en commun (Navigo...)", 40, "Mensuelle"),
        ("Entretien auto & pneumatiques", 400, "Annuelle")
    ],
    "Abonnements & Services": [
        ("Box Internet & Téléphones", 60, "Mensuelle"),
        ("Services de streaming & médias", 30, "Mensuelle"),
        ("Sport, clubs & loisirs", 45, "Mensuelle")
    ],
    "Assurances & Taxes hors immo": [
        ("Assurance habitation (MRH)", 240, "Annuelle"),
        ("Mutuelle santé (reste à charge)", 40, "Mensuelle")
    ],
    "Enfants & Famille": [
        ("Frais de garde / Nounou", 0, "Mensuelle"),
        ("Cantine & activités scolaires", 0, "Mensuelle")
    ],
    "Plaisir & Projets": [
        ("Vacances & Voyages", 2400, "Annuelle"),
        ("Habillement & shopping", 100, "Mensuelle")
    ]
}

depenses_liste = []

for cat, items in categories_def.items():
    with st.sidebar.expander(f"📁 {cat}", expanded=False):
        for item_nom, val_defaut, freq_defaut in items:
            col1, col2 = st.columns([2, 1])
            with col1:
                val = st.number_input(f"{item_nom}", min_value=0, value=val_defaut, step=10, key=f"val_{item_nom}")
            with col2:
                freq = st.selectbox("Fréquence", ["Mensuelle", "Annuelle"], index=0 if freq_defaut=="Mensuelle" else 1, key=f"freq_{item_nom}")
            
            cout_mensuel = val if freq == "Mensuelle" else val / 12
            if cout_mensuel > 0:
                depenses_liste.append({
                    "Nom": item_nom,
                    "Catégorie": cat,
                    "Montant Saisi": val,
                    "Fréquence": freq,
                    "Coût Mensuel": cout_mensuel
                })

df_depenses = pd.DataFrame(depenses_liste)
total_depenses_mensuelles = df_depenses["Coût Mensuel"].sum() if not df_depenses.empty else 0

# ---------------------------------------------------------
# CALCULS CLÉS
# ---------------------------------------------------------
taux_endettement = (pret_total / revenu_total * 100) if revenu_total > 0 else 0
reste_a_vivre_brut = revenu_total - pret_total
epargne_disponible = reste_a_vivre_brut - total_depenses_mensuelles

# ---------------------------------------------------------
# TABLEAU DE BORD PRINCIPAL
# ---------------------------------------------------------

# KPI Cards
kpi1, kpi2, kpi3, kpi4, kpi5 = st.columns(5)
kpi1.metric("Revenus Totaux", f"{revenu_total:,.0f} €/mois")
kpi2.metric("Mensualité Prêt", f"{pret_total:,.0f} €/mois", delta=f"Taux: {taux_endettement:.1f}%", delta_color="inverse" if taux_endettement > 35 else "normal")
kpi3.metric("Dépenses Courantes", f"{total_depenses_mensuelles:,.0f} €/mois")
kpi4.metric("Reste à Vivre Brut", f"{reste_a_vivre_brut:,.0f} €/mois")
kpi5.metric("Capacité d'Épargne Net", f"{epargne_disponible:,.0f} €/mois", delta="Bonus imprévus", delta_color="normal" if epargne_disponible > 0 else "inverse")

st.divider()

# Avertissement si taux > 35% ou reste négatif
if taux_endettement > 35:
    st.warning(f"⚠️ Attention : Votre taux d'endettement ({taux_endettement:.1f}%) dépasse le seuil légal/recommandé de 35%.")
if epargne_disponible < 0:
    st.error(f"🚨 Attention : Vos dépenses actuelles dépassent vos revenus après remboursement du prêt de {abs(epargne_disponible):,.0f} €/mois !")

# Onglets de Visualisation
tab1, tab2, tab3 = st.tabs(["📊 Répartition du Revenu & Dépenses", "🌊 Cascades du Cash-Flow", "📝 Détail des Dépenses"])

with tab1:
    col_chart1, col_chart2 = st.columns(2)
    
    with col_chart1:
        st.subheader("🍩 Répartition globale du Revenu")
        # Donut Chart 1 : Prêt vs Dépenses Courantes vs Reste à Épargner
        labels_globaux = ["Prêt Immobilier", "Dépenses Courantes", "Épargne / Dispo Net"]
        valeurs_globales = [pret_total, total_depenses_mensuelles, max(0, epargne_disponible)]
        
        fig_global = go.Figure(data=[go.Pie(
            labels=labels_globaux,
            values=valeurs_globales,
            hole=.5,
            marker_colors=['#E63946', '#457B9D', '#2A9D8F']
        )])
        fig_global.update_layout(margin=dict(t=30, b=0, l=0, r=0))
        st.plotly_chart(fig_global, use_container_width=True)

    with col_chart2:
        st.subheader("🥧 Ventilation des Dépenses par Catégorie")
        if not df_depenses.empty:
            df_cat = df_depenses.groupby("Catégorie")["Coût Mensuel"].sum().reset_index()
            fig_cat = px.pie(
                df_cat, 
                values="Coût Mensuel", 
                names="Catégorie", 
                hole=.4,
                color_discrete_sequence=px.colors.qualitative.Pastel
            )
            fig_cat.update_layout(margin=dict(t=30, b=0, l=0, r=0))
            st.plotly_chart(fig_cat, use_container_width=True)
        else:
            st.info("Aucune dépense courante renseignée.")

with tab2:
    st.subheader("🌊 Flux financier mensuel (Waterfall)")
    st.caption("Visualisez étape par étape comment votre revenu est consommé par les différentes charges.")
    
    # Graphique Cascade (Waterfall)
    waterfall_x = ["Revenu Net"]
    waterfall_y = [revenu_total]
    waterfall_measures = ["absolute"]
    
    waterfall_x.append("Prêt Immo")
    waterfall_y.append(-pret_total)
    waterfall_measures.append("relative")
    
    if not df_depenses.empty:
        df_cat = df_depenses.groupby("Catégorie")["Coût Mensuel"].sum().reset_index()
        for _, row in df_cat.iterrows():
            waterfall_x.append(row["Catégorie"])
            waterfall_y.append(-row["Coût Mensuel"])
            waterfall_measures.append("relative")
            
    waterfall_x.append("Reste Épargne")
    waterfall_y.append(epargne_disponible)
    waterfall_measures.append("total")

    fig_waterfall = go.Figure(go.Waterfall(
        name="Cashflow", orientation="v",
        measure=waterfall_measures,
        x=waterfall_x,
        textposition="outside",
        text=[f"{v:+,.0f} €" if m != "total" else f"{v:,.0f} €" for v, m in zip(waterfall_y, waterfall_measures)],
        y=waterfall_y,
        connector={"line":{"color":"rgb(63, 63, 63)"}},
        decreasing={"marker":{"color":"#E63946"}},
        increasing={"marker":{"color":"#2A9D8F"}},
        totals={"marker":{"color":"#1D3557"}}
    ))
    fig_waterfall.update_layout(margin=dict(t=30, b=0, l=0, r=0), showlegend=False)
    st.plotly_chart(fig_waterfall, use_container_width=True)

with tab3:
    st.subheader("📝 Détail complet des postes de dépenses")
    if not df_depenses.empty:
        st.dataframe(
            df_depenses.sort_values(by="Coût Mensuel", ascending=False).style.format({
                "Montant Saisi": "{:,.2f} €",
                "Coût Mensuel": "{:,.2f} €"
            }),
            use_container_width=True
        )
    else:
        st.info("Aucune dépense renseignée.")