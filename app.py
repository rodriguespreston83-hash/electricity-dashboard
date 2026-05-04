import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from datetime import time, timedelta

# ── Page Config ─────────────────────────────────────────────
st.set_page_config(page_title="Electricity Dashboard", layout="wide")

# ── Tariffs ─────────────────────────────────────────────────
TARIFFS = {
    "Standard Urban": {"type": "standard", "rate": 0.3762, "standing": 1.4416},
    "Standard Rural": {"type": "standard", "rate": 0.3762, "standing": 1.7296},
    "Urban NightSaver": {"type": "nightsaver", "day": 0.4206, "night": 0.2077, "standing": 1.7528},
    "Rural NightSaver": {"type": "nightsaver", "day": 0.4206, "night": 0.2077, "standing": 1.9821},
}

# ── Load Data ───────────────────────────────────────────────
def load_data(file):
    df = pd.read_csv(file) if file.name.endswith(".csv") else pd.read_excel(file)
    df.columns = df.columns.str.strip()

    # Auto detect columns
    time_col = [c for c in df.columns if "date" in c.lower()][0]
    value_col = [c for c in df.columns if "value" in c.lower()][0]

    df["timestamp"] = pd.to_datetime(df[time_col], errors="coerce", dayfirst=True)
    df["kWh"] = pd.to_numeric(df[value_col], errors="coerce").fillna(0)

    df = df.dropna(subset=["timestamp"]).sort_values("timestamp")
    df = df.set_index("timestamp").asfreq("30min", fill_value=0).reset_index()

    df["date"] = df["timestamp"].dt.date
    df["hour"] = df["timestamp"].dt.hour
    df["time"] = df["timestamp"].dt.strftime("%H:%M")
    df["weekday"] = df["timestamp"].dt.day_name()
    df["is_weekend"] = df["timestamp"].dt.dayofweek >= 5

    return df

# ── Night Logic ─────────────────────────────────────────────
def is_night(ts, start, end):
    t = ts.dt.time
    if start > end:
        return (t >= start) | (t < end)
    return (t >= start) & (t < end)

# ── Cost Calculation ────────────────────────────────────────
def apply_tariff(df, tariff, night_start, night_end):
    df = df.copy()

    if tariff["type"] == "standard":
        df["cost"] = df["kWh"] * tariff["rate"]
        df["period"] = "Standard"
    else:
        mask = is_night(df["timestamp"], night_start, night_end)
        df["period"] = np.where(mask, "Night", "Day")
        df["cost"] = np.where(
            df["period"] == "Night",
            df["kWh"] * tariff["night"],
            df["kWh"] * tariff["day"],
        )

    return df

# ── Sidebar ────────────────────────────────────────────────
st.sidebar.title("⚡ Controls")

uploaded = st.sidebar.file_uploader("Upload CSV/Excel", type=["csv", "xlsx"])

tariff_name = st.sidebar.selectbox("Tariff", list(TARIFFS.keys()))
tariff = TARIFFS[tariff_name]

night_start = time(23, 0)
night_end = time(8, 0)

if tariff["type"] == "nightsaver":
    night_start = time(st.sidebar.slider("Night Start", 0, 23, 23), 0)
    night_end = time(st.sidebar.slider("Night End", 0, 23, 8), 0)

# ── Main ───────────────────────────────────────────────────
st.title("⚡ Electricity Dashboard")

if uploaded is None:
    st.info("Upload a file to begin.")
    st.stop()

df = load_data(uploaded)
df = apply_tariff(df, tariff, night_start, night_end)

# ── Date Filter ─────────────────────────────────────────────
start, end = st.date_input("Date Range", [df["date"].min(), df["date"].max()])
df = df[(df["date"] >= start) & (df["date"] <= end)]

# ── Daily Aggregation ───────────────────────────────────────
daily = df.groupby("date").agg(
    kWh=("kWh", "sum"),
    cost=("cost", "sum")
).reset_index()

daily["cost"] += tariff["standing"]

# ── KPIs ───────────────────────────────────────────────────
col1, col2, col3 = st.columns(3)

col1.metric("Total kWh", f"{df['kWh'].sum():.1f}")
col2.metric("Total Cost €", f"{daily['cost'].sum():.2f}")
col3.metric("Avg Daily kWh", f"{daily['kWh'].mean():.2f}")

# ── Charts ─────────────────────────────────────────────────
tab1, tab2, tab3 = st.tabs(["Daily", "Heatmap", "Day vs Night"])

# Daily trend
with tab1:
    fig = px.line(daily, x="date", y="kWh", title="Daily Consumption")
    st.plotly_chart(fig, use_container_width=True)

    fig2 = px.line(daily, x="date", y="cost", title="Daily Cost")
    st.plotly_chart(fig2, use_container_width=True)

# Heatmap
with tab2:
    pivot = df.pivot_table(index="time", columns="date", values="kWh", aggfunc="sum")
    pivot = pivot.reindex(sorted(pivot.index))

    fig = go.Figure(go.Heatmap(
        z=pivot.values,
        x=pivot.columns,
        y=pivot.index,
        colorscale="RdYlBu_r"
    ))
    st.plotly_chart(fig, use_container_width=True)

# Day vs Night
with tab3:
    if tariff["type"] == "nightsaver":
        split = df.groupby("period")["kWh"].sum()

        fig = px.pie(
            values=split.values,
            names=split.index,
            title="Day vs Night Usage"
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Select a NightSaver tariff")

# ── Forecast ───────────────────────────────────────────────
st.subheader("📊 7-Day Forecast")

avg = daily["kWh"].tail(14).mean()
future = pd.date_range(daily["date"].max(), periods=7)

forecast = pd.DataFrame({
    "date": future,
    "kWh": avg
})

fig = go.Figure()
fig.add_trace(go.Scatter(x=daily["date"], y=daily["kWh"], name="Actual"))
fig.add_trace(go.Scatter(x=forecast["date"], y=forecast["kWh"], name="Forecast"))

st.plotly_chart(fig, use_container_width=True)
