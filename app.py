import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from datetime import time, timedelta

st.set_page_config(page_title="Electricity Dashboard", layout="wide")

# ── Tariffs ─────────────────────────────────────────────
TARIFFS = {
    "Standard Urban": {"type": "standard", "rate": 0.3762, "standing": 1.4416},
    "Standard Rural": {"type": "standard", "rate": 0.3762, "standing": 1.7296},
    "Urban NightSaver": {"type": "nightsaver", "day": 0.4206, "night": 0.2077, "standing": 1.7528},
    "Rural NightSaver": {"type": "nightsaver", "day": 0.4206, "night": 0.2077, "standing": 1.9821},
}

# ── Load Data ───────────────────────────────────────────
def load_data(file):
    df = pd.read_csv(file) if file.name.endswith(".csv") else pd.read_excel(file)
    df.columns = df.columns.str.strip()

    # Auto-detect columns
    time_col = next((c for c in df.columns if "date" in c.lower()), None)
    value_col = next((c for c in df.columns if "value" in c.lower()), None)

    if not time_col or not value_col:
        raise ValueError("Required columns not found")

    df["timestamp"] = pd.to_datetime(df[time_col], dayfirst=True, errors="coerce")
    df["kWh"] = pd.to_numeric(df[value_col], errors="coerce").fillna(0)

    df = df.dropna(subset=["timestamp"])

    # 🔥 FIX: handle duplicates
    dupes = df["timestamp"].duplicated().sum()
    if dupes > 0:
        st.warning(f"⚠️ {dupes} duplicate timestamps found — merged automatically")
        df = df.groupby("timestamp", as_index=False)["kWh"].sum()

    df = df.sort_values("timestamp")

    # Fill missing 30-min intervals
    df = df.set_index("timestamp").asfreq("30min", fill_value=0).reset_index()

    # Time features
    df["date"] = df["timestamp"].dt.date
    df["hour"] = df["timestamp"].dt.hour
    df["time"] = df["timestamp"].dt.strftime("%H:%M")
    df["weekday"] = df["timestamp"].dt.day_name()
    df["is_weekend"] = df["timestamp"].dt.dayofweek >= 5

    return df

# ── Night Logic ─────────────────────────────────────────
def is_night(ts, start, end):
    t = ts.dt.time
    if start > end:
        return (t >= start) | (t < end)
    return (t >= start) & (t < end)

# ── Apply Tariff ─────────────────────────────────────────
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

# ── Sidebar ─────────────────────────────────────────────
st.sidebar.title("⚡ Controls")

uploaded = st.sidebar.file_uploader("Upload CSV/Excel", type=["csv", "xlsx"])

tariff_name = st.sidebar.selectbox("Tariff", list(TARIFFS.keys()))
tariff = TARIFFS[tariff_name]

night_start = time(23, 0)
night_end = time(8, 0)

if tariff["type"] == "nightsaver":
    night_start = time(st.sidebar.slider("Night Start", 0, 23, 23), 0)
    night_end = time(st.sidebar.slider("Night End", 0, 23, 8), 0)

# ── Main ───────────────────────────────────────────────
st.title("⚡ Electricity Dashboard")

if uploaded is None:
    st.info("Upload a file to begin")
    st.stop()

df = load_data(uploaded)
df = apply_tariff(df, tariff, night_start, night_end)

# ── Date Filter ─────────────────────────────────────────
start, end = st.date_input(
    "Date Range",
    [df["date"].min(), df["date"].max()]
)

df = df[(df["date"] >= start) & (df["date"] <= end)]

if df.empty:
    st.warning("No data in selected range")
    st.stop()

# ── Daily Aggregation ───────────────────────────────────
daily = df.groupby("date").agg(
    kWh=("kWh", "sum"),
    cost=("cost", "sum")
).reset_index()

daily["cost"] += tariff["standing"]

# ── KPIs ───────────────────────────────────────────────
col1, col2, col3 = st.columns(3)

col1.metric("Total kWh", f"{df['kWh'].sum():.1f}")
col2.metric("Total Cost €", f"{daily['cost'].sum():.2f}")
col3.metric("Avg Daily kWh", f"{daily['kWh'].mean():.2f}")

# ── Tabs ───────────────────────────────────────────────
tab1, tab2, tab3 = st.tabs(["Daily", "Heatmap", "Day vs Night"])

# ── Daily Trends ───────────────────────────────────────
with tab1:
    fig1 = px.line(daily, x="date", y="kWh", title="Daily Consumption")
    st.plotly_chart(fig1, use_container_width=True)

    fig2 = px.line(daily, x="date", y="cost", title="Daily Cost")
    st.plotly_chart(fig2, use_container_width=True)

# ── Heatmap ────────────────────────────────────────────
with tab2:
    st.subheader("🔥 Advanced Heatmap")

    # ── Mode Toggle (like your JS)
    mode = st.radio("View Mode", ["Weekday x Hour", "Month x Hour"], horizontal=True)

    df_copy = df.copy()

    # ── Build matrix (same logic as your JS)
    if mode == "Weekday x Hour":
        df_copy["dow"] = df_copy["timestamp"].dt.dayofweek  # Mon=0
        grouped = df_copy.groupby(["dow", "hour"])["kWh"].mean().reset_index()

        pivot = grouped.pivot(index="dow", columns="hour", values="kWh")

        # Reorder to Mon→Sun
        pivot = pivot.reindex([0,1,2,3,4,5,6])
        pivot.index = ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"]

        title = "Avg kWh per Interval — Weekday x Hour"

    else:
        df_copy["month"] = df_copy["timestamp"].dt.to_period("M").astype(str)
        grouped = df_copy.groupby(["month", "hour"])["kWh"].mean().reset_index()

        pivot = grouped.pivot(index="month", columns="hour", values="kWh")
        pivot = pivot.sort_index()

        title = "Avg kWh per Interval — Month x Hour"

    pivot = pivot.fillna(0)

    # ── Heatmap
    fig = go.Figure(go.Heatmap(
        z=pivot.values,
        x=[f"{h:02d}:00" for h in pivot.columns],
        y=pivot.index,
        colorscale=[
            [0.0, "#0d1117"],
            [0.3, "#1a3a5c"],
            [0.6, "#1d6fa4"],
            [0.85, "#f59e0b"],
            [1.0, "#ef4444"],
        ],
        hovertemplate="Time: %{x}<br>Row: %{y}<br>kWh: %{z:.4f}<extra></extra>"
    ))

    fig.update_layout(
        title=title,
        height=500,
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#94a3b8"),
    )

    st.plotly_chart(fig, use_container_width=True)

    # ── KPI Logic (same as your JS)
    st.markdown("### 📊 Heatmap Insights")

    hour_avg = df_copy.groupby("hour")["kWh"].mean()
    peak_hour = hour_avg.idxmax()

    night_avg = df_copy[df_copy["hour"].isin([0,1,2,3,4])]["kWh"].mean()
    midday_avg = df_copy[df_copy["hour"].isin([9,10,11,12,13])]["kWh"].mean()
    evening_avg = df_copy[df_copy["hour"].isin([18,19,20,21])]["kWh"].mean()

    total_kwh = df_copy["kWh"].sum()

    col1, col2, col3, col4, col5 = st.columns(5)

    col1.metric("Peak Hour", f"{peak_hour:02d}:00", f"{hour_avg.max():.3f} kWh")
    col2.metric("Night Avg", f"{night_avg*2000:.0f} W")
    col3.metric("Midday Avg", f"{midday_avg*2000:.0f} W")
    col4.metric("Evening Avg", f"{evening_avg*2000:.0f} W")
    col5.metric("Total Usage", f"{total_kwh:.1f} kWh")

    # ── Busiest Day (only for weekday mode)
    if mode == "Weekday x Hour":
        dow_avg = df_copy.groupby("weekday")["kWh"].mean()
        busiest_day = dow_avg.idxmax()

        st.info(f"🔥 Busiest Day: {busiest_day}")

# ── Day vs Night ───────────────────────────────────────
with tab3:
    if tariff["type"] == "nightsaver":
        split = df.groupby("period")["kWh"].sum()

        total = split.sum() if split.sum() > 0 else 1

        colA, colB = st.columns(2)
        colA.metric("Day %", f"{(split.get('Day',0)/total)*100:.1f}%")
        colB.metric("Night %", f"{(split.get('Night',0)/total)*100:.1f}%")

        fig = px.pie(values=split.values, names=split.index, title="Usage Split")
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Switch to NightSaver tariff")

# ── Forecast ───────────────────────────────────────────
st.subheader("📊 7-Day Forecast")

avg = daily["kWh"].tail(14).mean()
future_dates = pd.date_range(daily["date"].max(), periods=7)

forecast = pd.DataFrame({
    "date": future_dates,
    "kWh": avg
})

# Cost estimate
if tariff["type"] == "standard":
    forecast["cost"] = forecast["kWh"] * tariff["rate"] + tariff["standing"]
else:
    forecast["cost"] = (
        forecast["kWh"] * (0.6 * tariff["day"] + 0.4 * tariff["night"])
        + tariff["standing"]
    )

fig = go.Figure()
fig.add_trace(go.Scatter(x=daily["date"], y=daily["kWh"], name="Actual"))
fig.add_trace(go.Scatter(x=forecast["date"], y=forecast["kWh"], name="Forecast"))

st.plotly_chart(fig, use_container_width=True)
