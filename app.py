"""Saudi Renewable Integration & Curtailment Simulator."""

from __future__ import annotations

import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from surplusflex.model import Scenario, compare_strategies, run_simulation
from surplusflex.saudi_data import OFFICIAL_URL, load_project_catalog, portfolio_summary


st.set_page_config(page_title="SurplusFlex Saudi Simulator", page_icon="☀️", layout="wide")
st.markdown("""
<style>
  .stApp { background: #f5f6f3; color:#173b3f; }
  .block-container { max-width: 1500px; padding-top: 1.4rem; }
  h1, h2, h3, p, label { color: #173b3f; }
  h1, h2, h3 { letter-spacing: -0.02em; }
  div[data-testid="stMetric"] { background:white; border:1px solid #dfe5df; border-radius:14px; padding:14px 16px; }
  div[data-testid="stMetricLabel"] { color:#52645d; }
  .source-badge { display:inline-block; padding:4px 9px; margin-right:6px; border-radius:999px; font-size:.76rem; font-weight:700; }
  .official { background:#dff4e8; color:#166534; }
  .modeled { background:#fff1cf; color:#8a5a00; }
  .hero-note { border-left:5px solid #b78932; background:white; padding:12px 16px; border-radius:8px; color:#31463f; }
  .scenario-note { color:#64746e; font-size:.88rem; min-height:2.5rem; }
</style>
""", unsafe_allow_html=True)

catalog = load_project_catalog()
all_projects = catalog["Project"].tolist()

PRESETS = {
    "2023 portfolio": {"year": 2023, "day": "Typical weekday", "demand": 1.00, "scale": 0.25,
                       "note": "Six commissioned projects · 3.4 GW official capacity"},
    "2024 portfolio": {"year": 2024, "day": "Typical weekday", "demand": 1.00, "scale": 0.25,
                       "note": "Ten commissioned projects · 6.551 GW official capacity"},
    "2025 portfolio": {"year": 2025, "day": "Typical weekday", "demand": 1.00, "scale": 0.25,
                       "note": "Fifteen commissioned projects · 12.313 GW official capacity"},
    "Solar surplus": {"year": 2025, "day": "Spring solar surplus", "demand": 0.82, "scale": 0.28,
                      "note": "Low demand with strong midday solar production"},
    "Summer peak": {"year": 2025, "day": "Summer peak", "demand": 1.15, "scale": 0.25,
                    "note": "High system demand and reduced curtailment risk"},
}

if "preset" not in st.session_state:
    st.session_state.preset = "Solar surplus"
    st.session_state.portfolio_year = 2025
    st.session_state.operating_day = "Spring solar surplus"
    st.session_state.demand_scale = 0.82
    st.session_state.network_scale = 0.28
    st.session_state.selected_projects = all_projects.copy()


def apply_preset(name: str):
    preset = PRESETS[name]
    st.session_state.preset = name
    st.session_state.portfolio_year = preset["year"]
    st.session_state.operating_day = preset["day"]
    st.session_state.demand_scale = preset["demand"]
    st.session_state.network_scale = preset["scale"]
    st.session_state.selected_projects = catalog.loc[catalog["Operation year"] <= preset["year"], "Project"].tolist()


st.caption("MINISTRY OF ENERGY HACKATHON · WORKING PROTOTYPE")
st.title("Saudi Renewable Integration & Curtailment Simulator")
st.markdown("""
<div class="hero-note"><b>Build a Saudi renewable portfolio, stress it under different operating conditions, and test how storage and productive flexible demand can reduce network-constrained curtailment.</b></div>
<p><span class="source-badge official">OFFICIAL PROJECT DATA</span><span class="source-badge modeled">MODELED NETWORK & PROFILES</span></p>
""", unsafe_allow_html=True)

st.subheader("1 · Choose a starting scenario")
scenario_cols = st.columns(len(PRESETS))
for col, (name, preset) in zip(scenario_cols, PRESETS.items()):
    with col:
        if st.button(name, width="stretch", type="primary" if st.session_state.preset == name else "secondary"):
            apply_preset(name)
            st.rerun()
        st.markdown(f"<div class='scenario-note'>{preset['note']}</div>", unsafe_allow_html=True)

with st.sidebar:
    st.header("Build the scenario")
    selected_projects = st.multiselect("Commissioned Saudi projects", all_projects, key="selected_projects")
    if not selected_projects:
        st.error("Select at least one renewable project.")
        st.stop()

    st.selectbox("Operating day", ["Typical weekday", "Spring solar surplus", "Low-demand weekend", "Summer peak"], key="operating_day")
    day_defaults = {
        "Typical weekday": (1.00, 1.00, 1.00),
        "Spring solar surplus": (0.82, 1.08, 0.90),
        "Low-demand weekend": (0.72, 1.00, 1.00),
        "Summer peak": (1.15, 1.02, 0.80),
    }
    suggested_demand, suggested_solar, suggested_wind = day_defaults[st.session_state.operating_day]
    if st.button("Apply operating-day assumptions", width="stretch"):
        st.session_state.demand_scale = suggested_demand
        st.session_state.solar_weather = suggested_solar
        st.session_state.wind_weather = suggested_wind
        st.rerun()

    st.selectbox("Management strategy", ["No intervention", "Battery only", "Flexible load only", "Combined optimization"], index=3, key="strategy")
    st.slider("Demand multiplier", 0.60, 1.25, step=0.01, key="demand_scale")
    if "solar_weather" not in st.session_state: st.session_state.solar_weather = suggested_solar
    if "wind_weather" not in st.session_state: st.session_state.wind_weather = suggested_wind
    st.slider("Solar production multiplier", 0.60, 1.20, step=0.02, key="solar_weather")
    st.slider("Wind production multiplier", 0.60, 1.20, step=0.02, key="wind_weather")
    st.slider("Test-system capacity scale", 0.10, 0.45, step=0.01, key="network_scale",
              help="Scales official project capacities onto the representative IEEE 24-bus test system.")

    st.subheader("Flexible resources")
    battery_power = st.slider("Battery power (MW)", 0, 500, 180, 20)
    battery_energy = st.slider("Battery energy (MWh)", 0, 1500, 720, 60)
    flex_power = st.slider("Productive flexible load (MW)", 0, 400, 140, 20)
    flex_energy = st.slider("Daily flexible service (MWh)", 0, 1600, 840, 60)
    flex_bus = st.selectbox("Flexible-load proxy bus", [5, 7, 14, 15, 18, 21, 23], index=5)
    st.caption("Examples: desalination, hydrogen, data centers, EV charging or thermal storage.")

effective_flex_energy = min(flex_energy, flex_power * 24)
scenario = Scenario(
    selected_projects=tuple(selected_projects), portfolio_year=st.session_state.portfolio_year,
    operating_day=st.session_state.operating_day, network_scale=st.session_state.network_scale,
    demand_scale=st.session_state.demand_scale, solar_scale=st.session_state.solar_weather,
    wind_scale=st.session_state.wind_weather, battery_power_mw=battery_power,
    battery_energy_mwh=battery_energy, flexible_power_mw=flex_power,
    flexible_energy_mwh=effective_flex_energy, flexible_bus=flex_bus,
    strategy=st.session_state.strategy,
)

try:
    result = run_simulation(scenario)
except RuntimeError as exc:
    st.error(str(exc)); st.stop()

selected_catalog = result["portfolio"]
official = portfolio_summary(selected_catalog)
m = result["metrics"]

st.subheader("2 · Selected Saudi portfolio")
p1, p2, p3, p4 = st.columns(4)
p1.metric("Commissioned projects", f"{official['projects']}")
p2.metric("Official capacity", f"{official['capacity_mw'] / 1000:,.2f} GW")
p3.metric("Official investment", f"SAR {official['investment_sar_bn']:,.1f}B")
p4.metric("Estimated households", f"{official['households'] / 1_000_000:,.2f}M")

st.subheader("3 · Simulation result")
r1, r2, r3, r4 = st.columns(4)
r1.metric(f"Curtailment ({m['curtailment_pct']:.1f}%)", f"{m['curtailment_mwh']:,.0f} MWh")
r2.metric("Renewable utilization", f"{m['renewable_utilization_pct']:.1f}%")
r3.metric("Conventional generation cost", f"${m['generation_cost']:,.0f}")
r4.metric("Peak line loading", f"{m['max_line_loading_pct']:.1f}%")
st.caption(f"Solved locally in {m['solve_seconds']:.2f} seconds · Representative IEEE 24-bus network · Official capacity scaled by {scenario.network_scale:.0%}")

@st.cache_data(show_spinner=False)
def cached_comparison(scenario_dict):
    return compare_strategies(Scenario(**scenario_dict))

comparison = cached_comparison(scenario.__dict__)
baseline = comparison.set_index("Strategy").loc["No intervention"]
chosen = comparison.set_index("Strategy").loc[scenario.strategy]
avoided = max(0.0, baseline["Curtailment (MWh)"] - chosen["Curtailment (MWh)"])
avoided_pct = 100 * avoided / baseline["Curtailment (MWh)"] if baseline["Curtailment (MWh)"] > 0 else 0
cost_change = chosen["Generation cost ($)"] - baseline["Generation cost ($)"]

tabs = st.tabs(["Portfolio ledger", "24-hour operation", "Strategy comparison", "Network", "Recommendations", "Method & sources"])

with tabs[0]:
    left, right = st.columns([1.55, 1])
    with left:
        display = selected_catalog[["Project", "Region", "Technology", "Operation year", "Capacity MW", "Investment SAR bn", "LCOE halala/kWh", "Proxy bus"]].copy()
        display = display.rename(columns={"Proxy bus": "Modeled proxy bus"})
        st.dataframe(display, width="stretch", hide_index=True)
    with right:
        regional = selected_catalog.groupby(["Region", "Technology"], as_index=False)["Capacity MW"].sum()
        fig = px.bar(regional, x="Region", y="Capacity MW", color="Technology", color_discrete_map={"Solar": "#d6a126", "Wind": "#2b7a78"})
        fig.update_layout(height=430, margin=dict(l=10, r=10, t=30, b=10))
        st.plotly_chart(fig, width="stretch")
        st.info("Project facts are official. Proxy buses are transparent modeling assumptions, not actual interconnection points.")

with tabs[1]:
    h = result["hourly"]
    fig = go.Figure()
    for column, color in [("Base demand (MW)", "#17324d"), ("Renewable available (MW)", "#d99b20"),
                          ("Renewable used (MW)", "#238b57"), ("Flexible load (MW)", "#7654a8")]:
        fig.add_trace(go.Scatter(x=h["Hour"], y=h[column], name=column.replace(" (MW)", ""), line=dict(color=color, width=3)))
    fig.add_trace(go.Bar(x=h["Hour"], y=h["Curtailed (MW)"], name="Curtailment", marker_color="#c9514b", opacity=.55))
    fig.update_layout(height=530, xaxis_title="Hour", yaxis_title="MW on representative system", hovermode="x unified", barmode="overlay")
    st.plotly_chart(fig, width="stretch")
    st.dataframe(result["plants"].sort_values("Curtailed (MWh)", ascending=False), width="stretch", hide_index=True)

with tabs[2]:
    fig = px.bar(comparison, x="Strategy", y="Curtailment (MWh)", color="Strategy",
                 color_discrete_sequence=["#a03a34", "#c9892b", "#3578a8", "#2f855a"])
    fig.update_layout(height=420, showlegend=False)
    st.plotly_chart(fig, width="stretch")
    st.dataframe(comparison, width="stretch", hide_index=True)

with tabs[3]:
    st.subheader("Most heavily loaded representative lines")
    st.dataframe(result["lines"].head(15), width="stretch", hide_index=True)
    st.caption("Line numbers and limits belong to the IEEE 24-bus test system. They demonstrate why the location of flexibility matters.")

with tabs[4]:
    peak_hour = int(result["hourly"].loc[result["hourly"]["Curtailed (MW)"].idxmax(), "Hour"])
    top_plant = result["plants"].sort_values("Curtailed (MWh)", ascending=False).iloc[0]
    st.subheader("What changed")
    st.markdown(f"""
    **{scenario.strategy.upper()}**

    - Avoided renewable curtailment: **{avoided:,.0f} MWh ({avoided_pct:.1f}%)** relative to no intervention.
    - Renewable utilization: **{m['renewable_utilization_pct']:.1f}%**.
    - Conventional-generation cost change: **${cost_change:,.0f}** relative to no intervention.
    - Maximum modeled curtailment occurs around **hour {peak_hour}**.
    - The largest project-level curtailed volume is associated with **{top_plant['Plant']}** in the scaled proxy simulation.
    """)
    if m["curtailment_mwh"] > 1:
        st.warning(f"Residual curtailment remains {m['curtailment_mwh']:,.0f} MWh. Test additional flexibility at buses near the most constrained lines or increase productive-load capacity during the surplus window.")
    else:
        st.success("The selected resource portfolio absorbs nearly all modeled renewable surplus.")
    st.download_button("Download hourly results (CSV)", result["hourly"].to_csv(index=False), "surplusflex_hourly_results.csv", "text/csv")

with tabs[5]:
    st.markdown(f"""
    ### Data provenance

    <span class="source-badge official">OFFICIAL</span> Project names, regions, technology, commissioned year, capacity, investment, LCOE and estimated households are read from the **GASTAT Renewable Energy Statistics 2025 workbook**, sourced from the Ministry of Energy. [Open official source]({OFFICIAL_URL})

    <span class="source-badge modeled">MODELED</span> Hourly renewable profiles, regional-to-bus mapping, demand multipliers, generator marginal costs, network constraints and flexibility behavior are test-system assumptions.

    ### Interpretation boundary

    This is a planning and concept-demonstration simulator. It does not reproduce Saudi National Grid topology or real-time operations. Official project capacities are proportionally scaled onto the IEEE 24-bus network so users can study curtailment mechanisms and compare interventions transparently.

    ### Source normalization note

    The official project/capacity sheets label Dumat Al-Jandal as solar, while the investment and LCOE sheets identify it as wind. The simulator normalizes it to wind and preserves this note for auditability.
    """, unsafe_allow_html=True)

