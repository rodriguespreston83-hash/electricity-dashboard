import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from datetime import time

st.set_page_config(page_title="Electricity Dashboard", layout="wide")

st.markdown(
    """
    <style>
    .stApp {
        background: radial-gradient(circle at top left, #0f172a 0%, #020617 45%, #020617 100%);
    }
    .main h1, .main h2, .main h3 { color: #e2e8f0; }
    .main p, .main label, .main div { color: #cbd5e1; }

    .kpi-card {
        background: linear-gradient(145deg, rgba(30,41,59,0.95), rgba(15,23,42,0.9));
        border: 1px solid rgba(148,163,184,0.18);
        border-radius: 14px;
        padding: 1rem;
        box-shadow: 0 8px 24px rgba(2,6,23,0.35);
    }

    .kpi-label { color: #94a3b8; font-size: 0.85rem; margin-bottom: 0.25rem; }
    .kpi-value { color: #f8fafc; font-size: 1.6rem; font-weight: 700; }
    .kpi-sub { color: #38bdf8; font-size: 0.8rem; margin-top: 0.35rem; }
    </style>
    """,
    unsafe_allow_html=True
)

PLOT_THEME = dict(
    template="plotly_dark",
    color_discrete_sequence=["#38bdf8", "#f59e0b", "#22c55e", "#ef4444", "#a855f7"]
)

TARIFFS = {
    "Standard Urban": {"type": "standard", "rate": 0.3762, "standing": 1.4416},
    "Standard Rural": {"type": "standard", "rate": 0.3762, "standing": 1.7296},
    "Urban NightSaver": {"type": "nightsaver", "day": 0.4206, "night": 0.2077, "standing": 1.7528},
    "Rural NightSaver": {"type": "nightsaver", "day": 0.4206, "night": 0.2077, "standing": 1.9821}
}


def kpi_card(label, value, subtext):
    st.markdown(
        f"""
        <div class="kpi-card">
            <div class="kpi-label">{label}</div>
            <div class="kpi-value">{value}</div>
            <div class="kpi-sub">{subtext}</div>
        </div>
        """,
        unsafe_allow_html=True
    )


def load_data(file):
    df = pd.read_csv(file) if file.name.endswith("csv") else pd.read_excel(file)
    df.columns = df.columns.str.strip()

    time_col = next((c for c in df.columns if "date" in c.lower()), None)
    value_col = next((c for c in df.columns if "value" in c.lower()), None)

    if not time_col or not value_col:
        raise ValueError("Required columns not found")

    df["timestamp"] = pd.to_datetime(df[time_col], dayfirst=True, errors="coerce")
    df["kwh"] = pd.to_numeric(df[value_col], errors="coerce").fillna(0)

    df = df.dropna(subset=["timestamp"])

    if df["timestamp"].duplicated().sum() > 0:
        df = df.groupby("timestamp", as_index=False)["kwh"].sum()

    df = df.sort_values("timestamp")
    df = df.set_index("timestamp").asfreq("30min", fill_value=0).reset_index()

    df["date"] = df["timestamp"].dt.date
    df["hour"] = df["timestamp"].dt.hour
    df["weekday"] = df["timestamp"].dt.day_name()

    return df


def is_night(ts, start, end):
    t = ts.dt.time
    if start > end:
        return (t >= start) | (t < end)
    return (t >= start) & (t < end)


def apply_tariff(df, tariff, night_start, night_end):
    df = df.copy()

    if tariff["type"] == "standard":
        df["cost"] = df["kwh"] * tariff["rate"]
        df["period"] = "Standard"
    else:
        mask = is_night(df["timestamp"], night_start, night_end)
        df["period"] = np.where(mask, "Night", "Day")
        df["cost"] = np.where(
            df["period"] == "Night",
            df["kwh"] * tariff["night"],
            df["kwh"] * tariff["day"]
        )

    return df


st.sidebar.title("Controls")

file = st.sidebar.file_uploader("Upload file", type=["csv", "xlsx"])
tariff_name = st.sidebar.selectbox("Tariff", list(TARIFFS.keys()))
tariff = TARIFFS[tariff_name]

night_start = time(23, 0)
night_end = time(8, 0)

if tariff["type"] == "nightsaver":
    night_start = time(st.sidebar.slider("Night start", 0, 23, 23), 0)
    night_end = time(st.sidebar.slider("Night end", 0, 23, 8), 0)

st.title("Electricity Dashboard")

if file is None:
    st.info("Upload a file to continue")
    st.stop()

df = apply_tariff(load_data(file), tariff, night_start, night_end)

start, end = st.date_input("Date range", [df["date"].min(), df["date"].max()])
df = df[(df["date"] >= start) & (df["date"] <= end)]

daily = df.groupby("date").agg(kwh=("kwh", "sum"), cost=("cost", "sum")).reset_index()
daily["cost"] = daily["cost"] + tariff["standing"]

c1, c2, c3, c4 = st.columns(4)

with c1:
    kpi_card("Total Usage", f"{df['kwh'].sum():.1f} kwh", "Selected period")

with c2:
    kpi_card("Total Cost", f"€{daily['cost'].sum():.2f}", "Including standing charge")

with c3:
    kpi_card("Average Daily Usage", f"{daily['kwh'].mean():.2f} kwh", "Consumption")

with c4:
    kpi_card("Peak Day", str(daily.loc[daily["kwh"].idxmax(), "date"]), "Highest usage")

tab1, tab2, tab3, tab4 = st.tabs(["Daily Trends", "Heatmap", "Day vs Night", "Forecast"])

with tab1:
    fig = px.area(daily, x="date", y="kwh", title="Daily Usage", **PLOT_THEME)
    st.plotly_chart(fig, use_container_width=True)

    fig2 = px.bar(daily, x="date", y="cost", title="Daily Cost", **PLOT_THEME)
    st.plotly_chart(fig2, use_container_width=True)


with tab2:
    mode = st.radio("View", ["Weekday Hour", "Month Hour"], horizontal=True)

    temp = df.copy()

    if mode == "Weekday Hour":
        temp["dow"] = temp["timestamp"].dt.dayofweek
        grouped = temp.groupby(["dow", "hour"])["kwh"].mean().reset_index()
        pivot = grouped.pivot(index="dow", columns="hour", values="kwh")
        pivot.index = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        title = "Weekday Heatmap"
    else:
        temp["month"] = temp["timestamp"].dt.to_period("M").astype(str)
        grouped = temp.groupby(["month", "hour"])["kwh"].mean().reset_index()
        pivot = grouped.pivot(index="month", columns="hour", values="kwh")
        title = "Monthly Heatmap"

    fig = go.Figure(go.Heatmap(z=pivot.fillna(0).values))
    fig.update_layout(title=title)
    st.plotly_chart(fig, use_container_width=True)


with tab3:
    summary = df.groupby("period")["kwh"].sum().reset_index()

    pie = px.pie(summary, values="kwh", names="period", hole=0.5, title="Usage Split")
    st.plotly_chart(pie, use_container_width=True)

    bar = px.bar(summary, x="period", y="kwh", title="Consumption by Period", text_auto=True)
    st.plotly_chart(bar, use_container_width=True)


with tab4:
    avg = daily["kwh"].tail(14).mean()
    future = pd.date_range(daily["date"].max(), periods=7)

    forecast = pd.DataFrame({"date": future, "kwh": avg})

    if tariff["type"] == "standard":
        forecast["cost"] = forecast["kwh"] * tariff["rate"] + tariff["standing"]
    else:
        forecast["cost"] = forecast["kwh"] * ((tariff["day"] + tariff["night"]) / 2) + tariff["standing"]

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=daily["date"], y=daily["kwh"], name="Actual"))
    fig.add_trace(go.Scatter(x=forecast["date"], y=forecast["kwh"], name="Forecast"))

    fig.update_layout(title="Forecast", yaxis_title="kwh")
    st.plotly_chart(fig, use_container_width=True)
