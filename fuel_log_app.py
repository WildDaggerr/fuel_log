# -*- coding: utf-8 -*-
import os
import pandas as pd
import streamlit as st
import altair as alt
from supabase import create_client

# ------------------------------------------------------------
# SIDKONFIG
# ------------------------------------------------------------
st.set_page_config(page_title="Bränslelogg", page_icon="⛽", layout="wide")

# Lite tightare vertikal padding (valfritt)
st.markdown("""
    <style>
    .block-container {padding-top: 1rem; padding-bottom: 1rem;}
    section[data-testid="stSidebar"] {padding-top: 0.5rem;}
    .stMetric {text-align:center;}
    </style>
""", unsafe_allow_html=True)

# ------------------------------------------------------------
# SUPABASE – nycklar via Secrets / miljövariabler
# ------------------------------------------------------------
try:
    SUPABASE_URL = os.environ["SUPABASE_URL"]
    SUPABASE_KEY = os.environ["SUPABASE_KEY"]
except KeyError:
    st.error("Saknar SUPABASE_URL/SUPABASE_KEY. Lägg in dem i Streamlit Secrets.")
    st.stop()

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# ------------------------------------------------------------
# TITEL
# ------------------------------------------------------------
st.title("⛽ Bränslelogg")

# ------------------------------------------------------------
# FORMULÄR – Lägg till ny tankning (textfält för att undvika 0,00-problem)
# ------------------------------------------------------------
st.subheader("➕ Lägg till ny tankning")
with st.form("add_fuel", clear_on_submit=True):
    date = st.date_input("Datum")
    odo_text = st.text_input("Mätarställning (km)", placeholder="t.ex. 210123,5")
    liters_text = st.text_input("Liter tankat", placeholder="t.ex. 45,2")
    price_text = st.text_input("Pris per liter (kr)", placeholder="t.ex. 19,49")
    full = st.checkbox("Full tank")
    notes = st.text_input("Anteckningar", placeholder="Station, vägtyp, mm.")
    submit = st.form_submit_button("Spara")

    if submit:
        try:
            odo = float(odo_text.replace(",", "."))
            liters = float(liters_text.replace(",", "."))
            price = float(price_text.replace(",", "."))
            row = {
                "date": str(date),
                "odometer_km": odo,
                "liters": liters,
                "price_per_liter": price,
                "full_fill": full,
                "notes": notes,
            }
            supabase.table("fuel_log").insert(row).execute()
            st.success("✅ Tankning sparad i databasen!")
        except ValueError:
            st.error("❌ Fel: Kontrollera att mätarställning, liter och pris är siffror.")

st.divider()

# ------------------------------------------------------------
# HÄMTA DATA
# ------------------------------------------------------------
res = supabase.table("fuel_log").select("*").order("date", desc=True).execute()
df = pd.DataFrame(res.data if res.data else [])

if not df.empty:
    # Säkerställ numeriska typer
    for col in ["odometer_km", "liters", "price_per_liter"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # --------------------------------------------------------
    # BERÄKNINGAR FÖR METRICS & GRAFER
    # --------------------------------------------------------
    df_sorted_odo = df.sort_values("odometer_km")
    total_km = float(df_sorted_odo["odometer_km"].iloc[-1] - df_sorted_odo["odometer_km"].iloc[0])
    total_liters = float(df_sorted_odo["liters"].sum(skipna=True))
    total_cost = float((df_sorted_odo["liters"] * df_sorted_odo["price_per_liter"]).sum(skipna=True))
    avg_consumption = (total_liters / total_km) * 100 if total_km > 0 else 0.0

    # För grafer (sortera på datum)
    df_sorted = df.copy()
    df_sorted["date"] = pd.to_datetime(df_sorted["date"])
    df_sorted = df_sorted.sort_values("date")
    df_sorted["total_cost"] = df_sorted["liters"] * df_sorted["price_per_liter"]
    df_sorted["km_diff"] = df_sorted["odometer_km"].diff()
    valid = df_sorted["km_diff"] > 0
    df_sorted.loc[valid, "l_per_100km_entry"] = (
        df_sorted.loc[valid, "liters"] / df_sorted.loc[valid, "km_diff"]
    ) * 100
    df_sorted.loc[~valid, "l_per_100km_entry"] = None

    # --------------------------------------------------------
    # FLIKAR: Översikt (metrics+grafer) & Historik (tabell)
    # --------------------------------------------------------
    tab_overview, tab_history = st.tabs(["📊 Översikt", "📋 Historik"])

    with tab_overview:
        # Metrics i en rad
        col1, col2, col3 = st.columns(3)
        col1.metric("🚗 Snittförbrukning", f"{avg_consumption:.1f} L/100 km")
        col2.metric("⛽ Totalt tankat", f"{total_liters:.1f} L")
        col3.metric("💰 Totalkostnad", f"{total_cost:,.0f} kr")

        # Grafer bredvid varandra
        st.markdown("### ")
        colA, colB = st.columns(2)

        with colA:
            st.markdown("#### 📈 Förbrukning över tid")
            cons_series = df_sorted.set_index("date")["l_per_100km_entry"].dropna()
            if not cons_series.empty:
                chart = alt.Chart(cons_series.reset_index()).mark_line(point=True).encode(
                    x=alt.X("date:T", title="Datum"),
                    y=alt.Y("l_per_100km_entry:Q", title="L/100 km")
                ).properties(height=250)
                st.altair_chart(chart, use_container_width=True)
            else:
                if total_km > 0:
                    st.info("Visar snitt då det saknas parvisa mätningar.")
                    chart = alt.Chart(pd.DataFrame({
                        "date": [df_sorted["date"].iloc[-1]],
                        "l_per_100km_entry": [avg_consumption]
                    })).mark_point(size=80).encode(
                        x="date:T",
                        y="l_per_100km_entry:Q"
                    ).properties(height=250)
                    st.altair_chart(chart, use_container_width=True)
                else:
                    st.info("Behöver minst två mätningar med ökande mätarställning.")

        with colB:
            st.markdown("#### 💸 Kostnad per månad")
            month_cost = (
                df_sorted.assign(month=df_sorted["date"].dt.to_period("M").astype(str))
                         .groupby("month", as_index=True)["total_cost"].sum()
                         .sort_index()
            )
            if not month_cost.empty:
                chart2 = alt.Chart(month_cost.reset_index()).mark_bar().encode(
                    x=alt.X("month:N", title="Månad"),
                    y=alt.Y("total_cost:Q", title="Kostnad (kr)")
                ).properties(height=250)
                st.altair_chart(chart2, use_container_width=True)
            else:
                st.info("Ingen kostnadsdata ännu.")

    with tab_history:
        st.markdown("#### Tankningshistorik")
        df_view = df[["date", "odometer_km", "liters", "price_per_liter", "full_fill", "notes"]].copy()
        df_view = df_view.rename(columns={
            "date": "Datum",
            "odometer_km": "Mätarställning (km)",
            "liters": "Liter",
            "price_per_liter": "Pris/liter (kr)",
            "full_fill": "Full tank",
            "notes": "Anteckningar",
        })
        st.dataframe(df_view, use_container_width=True)

else:
    st.info("ℹ️ Inga poster ännu – lägg till en tankning!")
