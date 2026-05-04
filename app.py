import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import time

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Electricity Cost Dashboard",
    page_icon="⚡",
    layout="wide",
)

# ── Tariff definitions ────────────────────────────────────────────────────────
TARIFFS = {
    "PrepayPower Standard 24 Hr Urban": {
        "type": "standard",
        "unit_rate": 0.3762,
        "standing_charge": 1.4416,
    },
    "PrepayPower Standard 24 Hr Rural": {
        "type": "standard",
        "unit_rate": 0.3762,
        "standing_charge": 1.7296,
    },
    "PrepayPower Urban NightSaver": {
        "type": "nightsaver",
        "day_rate": 0.4206,
        "night_rate": 0.2077,
        "standing_charge": 1.7528,
    },
    "PrepayPower Rural NightSaver": {
        "type": "nightsaver",
        "day_rate": 0.4206,
        "night_rate": 0.2077,
        "standing_charge": 1.9821,
    },
}

# ── Helpers ───────────────────────────────────────────────────────────────────

def load_data(file) -> pd.DataFrame:
    """Load CSV or Excel, parse timestamps, sort."""
    if file.name.endswith(".csv"):
        df = pd.read_csv(file)
    else:
        df = pd.read_excel(file)

    df.columns = df.columns.str.strip()

    # Flexible timestamp parsing
    df["timestamp"] = pd.to_datetime(
        df["Read Date and End Time"],
        dayfirst=True,
        errors="coerce",
    )
    df = df.dropna(subset=["timestamp"])
    df = df.sort_values("timestamp").reset_index(drop=True)
    df["date"] = df["timestamp"].dt.date
    df["hour"] = df["timestamp"].dt.hour
    df["minute"] = df["timestamp"].dt.minute
    df["kWh"] = pd.to_numeric(df["Read Value"], errors="coerce").fillna(0)
    return df


def is_night(ts: pd.Series, night_start: time, night_end: time) -> pd.Series:
    """Return boolean Series: True when timestamp falls in night period.
    Night period wraps midnight, e.g. 23:00 → 08:00.
    """
    t = ts.dt.time
    if night_start > night_end:  # wraps midnight (normal case)
        return (t >= night_start) | (t < night_end)
    else:  # unusual: night period within same day
        return (t >= night_start) & (t < night_end)


def calculate_costs(df: pd.DataFrame, tariff: dict, night_start: time, night_end: time) -> pd.DataFrame:
    """Add cost column and return daily aggregates."""
    df = df.copy()

    if tariff["type"] == "standard":
        df["cost"] = df["kWh"] * tariff["unit_rate"]
        df["period"] = "Standard"
    else:
        night_mask = is_night(df["timestamp"], night_start, night_end)
        df["period"] = night_mask.map({True: "Night", False: "Day"})
        df["cost"] = df.apply(
            lambda r: r["kWh"] * (tariff["night_rate"] if r["period"] == "Night" else tariff["day_rate"]),
            axis=1,
        )

    # Daily aggregates
    daily = (
        df.groupby("date")
        .agg(daily_kwh=("kWh", "sum"), daily_cost=("cost", "sum"))
        .reset_index()
    )
    daily["daily_cost"] += tariff["standing_charge"]  # add standing charge per day

    return df, daily


# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("⚡ Settings")

    uploaded = st.file_uploader(
        "Upload electricity data (CSV or Excel)",
        type=["csv", "xlsx", "xls"],
        help="File must contain 'Read Date and End Time' and 'Read Value' columns.",
    )

    st.divider()

    tariff_name = st.selectbox("Tariff", list(TARIFFS.keys()))
    tariff = TARIFFS[tariff_name]

    st.divider()

    # Night time controls — only shown for NightSaver tariffs
    night_start = time(23, 0)
    night_end = time(8, 0)
    if tariff["type"] == "nightsaver":
        st.subheader("🌙 Night Period")
        night_start_h = st.slider("Night starts (hour)", 0, 23, 23)
        night_end_h = st.slider("Night ends (hour)", 0, 23, 8)
        night_start = time(night_start_h, 0)
        night_end = time(night_end_h, 0)
        st.caption(f"Night: {night_start.strftime('%H:%M')} → {night_end.strftime('%H:%M')}")

    st.divider()
    st.caption("Rates shown include VAT. Standing charges are per day (€).")

# ── Main ──────────────────────────────────────────────────────────────────────
st.title("⚡ Electricity Cost Dashboard")

if uploaded is None:
    st.info("👈 Upload your electricity usage file from the sidebar to get started.")
    st.markdown(
        """
        **Expected columns:**
        - `Read Date and End Time` — interval timestamp (e.g. `01-05-2026 05:00`)
        - `Read Value` — energy consumed in kWh for that interval
        """
    )
    st.stop()

# Load & process
with st.spinner("Loading data…"):
    try:
        raw = load_data(uploaded)
    except Exception as e:
        st.error(f"Could not parse file: {e}")
        st.stop()

# ── Date range filter ─────────────────────────────────────────────────────────
min_date = raw["date"].min()
max_date = raw["date"].max()

col_l, col_r = st.columns(2)
with col_l:
    start_date = st.date_input("From", value=min_date, min_value=min_date, max_value=max_date)
with col_r:
    end_date = st.date_input("To", value=max_date, min_value=min_date, max_value=max_date)

if start_date > end_date:
    st.error("'From' date must be before 'To' date.")
    st.stop()

mask = (raw["date"] >= start_date) & (raw["date"] <= end_date)
filtered = raw[mask].copy()

if filtered.empty:
    st.warning("No data in the selected date range.")
    st.stop()

# ── Calculate costs ───────────────────────────────────────────────────────────
interval_df, daily_df = calculate_costs(filtered, tariff, night_start, night_end)

# ── KPI cards ─────────────────────────────────────────────────────────────────
total_kwh = filtered["kWh"].sum()
total_cost = daily_df["daily_cost"].sum()
avg_daily_cost = daily_df["daily_cost"].mean()
num_days = len(daily_df)

k1, k2, k3, k4 = st.columns(4)
k1.metric("⚡ Total Consumption", f"{total_kwh:,.2f} kWh")
k2.metric("💶 Total Cost", f"€{total_cost:,.2f}")
k3.metric("📅 Avg Daily Cost", f"€{avg_daily_cost:,.2f}")
k4.metric("📆 Days", num_days)

st.divider()

# ── Charts ────────────────────────────────────────────────────────────────────
c1, c2 = st.columns(2)

with c1:
    st.subheader("Daily Consumption (kWh)")
    fig_kwh = px.line(
        daily_df,
        x="date",
        y="daily_kwh",
        labels={"date": "Date", "daily_kwh": "kWh"},
        color_discrete_sequence=["#4F8EF7"],
    )
    fig_kwh.update_traces(line_width=1.5)
    fig_kwh.update_layout(margin=dict(t=10, b=10), hovermode="x unified")
    st.plotly_chart(fig_kwh, use_container_width=True)

with c2:
    st.subheader("Daily Cost (€)")
    fig_cost = px.line(
        daily_df,
        x="date",
        y="daily_cost",
        labels={"date": "Date", "daily_cost": "Cost (€)"},
        color_discrete_sequence=["#F7844F"],
    )
    fig_cost.update_traces(line_width=1.5)
    fig_cost.update_layout(margin=dict(t=10, b=10), hovermode="x unified")
    st.plotly_chart(fig_cost, use_container_width=True)

# Day vs Night bar chart (NightSaver only)
if tariff["type"] == "nightsaver":
    st.subheader("Day vs Night Usage (kWh)")
    dn = (
        interval_df.groupby(["date", "period"])["kWh"]
        .sum()
        .reset_index()
    )
    fig_dn = px.bar(
        dn,
        x="date",
        y="kWh",
        color="period",
        barmode="stack",
        color_discrete_map={"Day": "#F7C94F", "Night": "#4F5EF7"},
        labels={"date": "Date", "kWh": "kWh", "period": "Period"},
    )
    fig_dn.update_layout(margin=dict(t=10, b=10), hovermode="x unified")
    st.plotly_chart(fig_dn, use_container_width=True)

    # Summary table
    st.subheader("Day / Night Summary")
    summary = (
        interval_df.groupby("period")
        .agg(total_kwh=("kWh", "sum"), total_cost=("cost", "sum"))
        .reset_index()
    )
    summary.columns = ["Period", "Total kWh", "Energy Cost (€)"]
    summary["Total kWh"] = summary["Total kWh"].map("{:,.3f}".format)
    summary["Energy Cost (€)"] = summary["Energy Cost (€)"].map("€{:,.2f}".format)
    st.dataframe(summary, hide_index=True, use_container_width=True)

# ── Tariff info box ───────────────────────────────────────────────────────────
with st.expander("📋 Selected Tariff Details"):
    t = tariff.copy()
    if t["type"] == "standard":
        st.markdown(f"""
| | |
|---|---|
| **Tariff** | {tariff_name} |
| **Unit Rate** | €{t['unit_rate']:.4f} / kWh |
| **Standing Charge** | €{t['standing_charge']:.4f} / day |
""")
    else:
        st.markdown(f"""
| | |
|---|---|
| **Tariff** | {tariff_name} |
| **Day Rate (€/kWh)** | €{t['day_rate']:.4f} |
| **Night Rate (€/kWh)** | €{t['night_rate']:.4f} |
| **Standing Charge** | €{t['standing_charge']:.4f} / day |
| **Night Period** | {night_start.strftime('%H:%M')} → {night_end.strftime('%H:%M')} |
""")
