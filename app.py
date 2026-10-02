import plotly.graph_objects as go
import streamlit as st

from engine import Scenario, ZONES, allocation_totals, build_world, manual_zone_share, optimise, plan_summary, simulate


st.set_page_config(page_title="MIRROR | Disaster Consequence Simulator", page_icon="◈", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
<style>
    .stApp { background: #07131d; color: #edf6fb; }
    [data-testid="stSidebar"] { background: #0b1c28; border-right: 1px solid #1b3a4b; }
    h1, h2, h3 { color: #f2f7f8 !important; }
    .eyebrow { color:#4be0b7; font-size:.76rem; letter-spacing:.14em; font-weight:700; }
    .hero { padding: 1.2rem 0 .7rem; }
    .hero h1 { font-size: 2.7rem; margin: .15rem 0; }
    .hero p { color:#aabec9; font-size:1.05rem; }
    .card { background:#0d2432; border:1px solid #1b4051; border-radius:14px; padding:1rem 1.1rem; height:100%; }
    .status { display:inline-block; border:1px solid #1f594c; color:#57e2b7; background:#0d302b; border-radius:999px; padding:.22rem .65rem; font-size:.78rem; }
    .stButton>button { background:#18b889; border:0; color:#03120e; font-weight:750; border-radius:8px; padding:.6rem 1rem; width:100%; }
    .stMetric { background:#0d2432; border:1px solid #1b4051; border-radius:12px; padding:.65rem; }
    .stTabs [data-baseweb="tab"] { color:#afc0c9; }
</style>
""", unsafe_allow_html=True)


def make_scenario() -> Scenario:
    return Scenario(
        disaster=st.session_state.get("disaster", "Flood"),
        population=st.session_state.get("population", 50000),
        rescue_teams=st.session_state.get("teams", 8),
        boats=st.session_state.get("boats", 15),
        ambulances=st.session_state.get("ambulances", 6),
        hospitals=st.session_state.get("hospitals", 3),
        roads_blocked=st.session_state.get("roads", 30),
        weather_intensity=st.session_state.get("weather", 7),
    )


def run_plan(scenario: Scenario, mode: str = "optimise", target: str = "A", share: int = 60) -> dict:
    world = build_world(scenario)
    allocation = optimise(world, scenario.resources) if mode == "optimise" else manual_zone_share(world, scenario.resources, target, share)
    forecast = simulate(world, allocation)
    return {"scenario": scenario, "world": world, "allocation": allocation, "forecast": forecast, "mode": mode, "target": target, "share": share}


def zone_color(severity: float) -> str:
    """Returns color based on zone severity status: Red, Orange, Yellow, Green."""
    if severity >= 80:
        return "#ff4d5d"  # Red: Critical
    if severity >= 60:
        return "#ffaf3d"  # Orange: Strained
    if severity >= 40:
        return "#f7d070"  # Yellow: Elevated Warning
    return "#45dca2"      # Green: Stabilising


def get_zone_status_label(severity: float) -> str:
    if severity >= 80:
        return "RED (Critical)"
    if severity >= 60:
        return "ORANGE (Strained)"
    if severity >= 40:
        return "YELLOW (Warning)"
    return "GREEN (Stabilising)"


def map_figure(snapshot: dict) -> go.Figure:
    positions = {"A": (0, 1), "B": (1.4, .1), "C": (2.8, 1.05)}
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=[0, 1.4, 2.8], y=[1, .1, 1.05], mode="lines", line=dict(color="#33596a", width=6), hoverinfo="skip"))
    for zone in ZONES:
        data = snapshot["zones"][zone]
        x, y = positions[zone]
        status_text = get_zone_status_label(data["severity"])
        fig.add_trace(go.Scatter(
            x=[x], y=[y], mode="markers+text", text=[f"<b>ZONE {zone}</b><br>{data['people_in_danger']:,} at risk"],
            textposition="bottom center", textfont=dict(color="#e9f2f5", size=13),
            marker=dict(size=76, color=zone_color(data["severity"]), line=dict(color="#eaf7f4", width=2)),
            hovertemplate=f"<b>Zone {zone}</b><br>Status: {status_text}<br>Severity: {data['severity']:.0f}/100<br>Road access: {'Open' if data['road_access'] else 'Blocked'}<br>Rescued this hour: {data['rescued_this_hour']:,}<extra></extra>",
        ))
    fig.update_layout(height=390, margin=dict(l=5, r=5, t=20, b=25), paper_bgcolor="#0d2432", plot_bgcolor="#0d2432", showlegend=False,
                      xaxis=dict(visible=False, range=[-.65, 3.45]), yaxis=dict(visible=False, range=[-.6, 1.7], scaleanchor="x", scaleratio=1))
    return fig


def allocation_table(allocation: dict) -> list:
    return [{"Zone": f"Zone {z}", "Teams": allocation[z]["rescue_teams"], "Boats": allocation[z]["boats"], "Ambulances": allocation[z]["ambulances"]} for z in ZONES]


with st.sidebar:
    st.markdown("### ◈ MIRROR")
    st.caption("COMMAND CONSOLE")
    st.selectbox("Disaster type", ["Flood", "Cyclone", "Earthquake", "Wildfire"], key="disaster")
    st.number_input("Population exposed", min_value=1_000, max_value=2_000_000, value=50_000, step=1_000, key="population")
    st.markdown("#### Available response assets")
    a, b = st.columns(2)
    a.number_input("Rescue teams", 0, 100, 8, key="teams")
    b.number_input("Boats", 0, 100, 15, key="boats")
    a, b = st.columns(2)
    a.number_input("Ambulances", 0, 100, 6, key="ambulances")
    b.number_input("Hospitals", 1, 20, 3, key="hospitals")
    st.slider("Road network blocked", 0, 100, 30, format="%d%%", key="roads")
    st.slider("Weather intensity", 1, 10, 7, key="weather")
    st.divider()
    if st.button("✦ Generate AI plan", type="primary"):
        st.session_state.result = run_plan(make_scenario())
        st.session_state.baseline = st.session_state.result
    st.caption("Model version 1.0 · Offline capable")

if "result" not in st.session_state:
    st.session_state.result = run_plan(make_scenario())
    st.session_state.baseline = st.session_state.result

result = st.session_state.result
forecast = result["forecast"]
hour = st.session_state.get("map_hour", 6)
snapshot = forecast[hour - 1]

st.markdown("""<div class="hero"><div class="eyebrow">AI DISASTER CONSEQUENCE SIMULATOR</div><h1>See the consequences before they happen.</h1><p>Model response options in real time, then act on the safest future.</p><span class="status">● LIVE WORLD MODEL</span></div>""", unsafe_allow_html=True)

# Popup / Evacuation alert checking
zones_needing_evacuation = [
    z for z, data in snapshot["zones"].items() 
    if data["severity"] >= 80 or (data["severity"] >= 60 and not data["road_access"])
]

if zones_needing_evacuation:
    st.error(
        f"🚨 **IMMEDIATE RELOCATION REQUIRED**: Zone(s) {', '.join(zones_needing_evacuation)} "
        f"are in a critical condition (Severity ≥ 80 or roads blocked with high risk). Issue emergency evacuation orders immediately!"
    )
else:
    st.info("ℹ️ **NO IMMEDIATE RELOCATION REQUIRED**: Evacuation thresholds have not been breached for the current forecast hour.")

top_a, top_b, top_c, top_d = st.columns(4)
top_a.metric("People rescued", f"{snapshot['cumulative_rescued']:,}", f"by hour {hour}")
top_b.metric("People still at risk", f"{sum(z['people_in_danger'] for z in snapshot['zones'].values()):,}")
top_c.metric("Critical zones", len(snapshot["critical_zones"]), ", ".join(snapshot["critical_zones"]) or "None")
top_d.metric("Peak hospital load", f"{max(h['load_percent'] for h in snapshot['hospitals'].values())}%")

left, right = st.columns([1.28, .72], gap="large")
with left:
    st.markdown("### Live city response map")
    st.select_slider("Forecast time", options=list(range(1, 13)), value=hour, format_func=lambda h: f"Hour {h}", key="map_hour")
    snapshot = forecast[st.session_state.map_hour - 1]
    st.plotly_chart(map_figure(snapshot), use_container_width=True, config={"displayModeBar": False})
    st.caption("🔴 Red = Critical · 🟠 Orange = Strained · 🟡 Yellow = Warning · 🟢 Green = Stabilising. Hover a zone for operational details.")
with right:
    st.markdown("### Current plan")
    st.dataframe(allocation_table(result["allocation"]), hide_index=True, use_container_width=True)
    totals = allocation_totals(result["allocation"])
    st.caption(f"Deployed: {totals['rescue_teams']} teams · {totals['boats']} boats · {totals['ambulances']} ambulances")
    st.markdown("#### Tactical briefing")
    for point in plan_summary(result["world"], result["allocation"], result["forecast"]):
        st.write("• " + point)

st.divider()
st.markdown("### Try another future")
st.caption("Force a response decision, then compare the new future with the AI-recommended baseline.")
sim_a, sim_b, sim_c = st.columns([1, 1, 1.2])
with sim_a:
    target_zone = st.selectbox("Send resources to", list(ZONES), format_func=lambda z: f"Zone {z}")
with sim_b:
    forced_share = st.slider("Share of every resource", 0, 100, 60, format="%d%%")
with sim_c:
    st.write("")
    st.write("")
    if st.button("Simulate this decision"):
        st.session_state.result = run_plan(make_scenario(), "manual", target_zone, forced_share)
        result = st.session_state.result
        forecast = result["forecast"]

result = st.session_state.result
baseline = st.session_state.baseline
now = result["forecast"][-1]
base = baseline["forecast"][-1]
comparison = now["cumulative_rescued"] - base["cumulative_rescued"]
c1, c2, c3 = st.columns(3)
c1.metric("12-hour rescued", f"{now['cumulative_rescued']:,}", f"{comparison:+,} vs baseline")
c2.metric("12-hour critical zones", len(now["critical_zones"]), f"{len(now['critical_zones']) - len(base['critical_zones']):+d} vs baseline")
c3.metric("Highest hospital load", f"{max(h['load_percent'] for h in now['hospitals'].values())}%")

with st.expander("How MIRROR produces this forecast"):
    st.markdown("**World model:** zones, people at risk, hospital capacity and road access.  ")
    st.markdown("**Prediction layer:** deterministic hourly rescue, severity and hospital-load rules.  ")
    st.markdown("**Optimisation layer:** assigns each scarce asset by its marginal benefit, including diminishing returns.  ")
    st.markdown("**Explanation layer:** turns only the computed forecast into the tactical briefing above.")
