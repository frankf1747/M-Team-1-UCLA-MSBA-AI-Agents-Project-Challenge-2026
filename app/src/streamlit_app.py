"""Minimalist Streamlit UI for the SeeWeeS What-if Scenario Simulation.

Run from the app/ directory:
    streamlit run src/streamlit_app.py
"""
from __future__ import annotations
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

import pandas as pd
import streamlit as st
import matplotlib.pyplot as plt

from viz.cowork_trace import stream_graph, HANDOFF

st.set_page_config(page_title="SeeWeeS What-if Simulation", layout="wide")
st.title("SeeWeeS — What-if Scenario Simulation")
st.caption("Pressure-test the 48h dispatch plan before disruptions happen.")

DEFAULT_CSV = "data-augmented/incoming_shipments_scenario.csv"
DEFAULT_PDF = "data/SeeWeeS Specialty distribution.pdf"

# ---------------- sidebar: scenario builder ----------------
with st.sidebar:
    st.header("Scenario builder")
    offline = st.checkbox("Offline mode (no API key, deterministic stubs)", value=True)
    demand = st.slider("Demand spike (%)", 0, 100, 0, step=5)
    closure = st.selectbox("Close a corridor / warehouse",
                           ["(none)", "C1_I95_NJ_BOS", "C2_NJ_PHL"])
    st.markdown("**Resource availability (per day)**")
    drivers = st.number_input("Drivers", 0, 20, 6)
    std_trucks = st.number_input("Standard trucks", 0, 20, 4)
    reefer_trucks = st.number_input("Temp-controlled trucks", 0, 20, 2)
    st.markdown("**Weather override**")
    wx_corridor = st.selectbox("Corridor", ["(none)", "C1_I95_NJ_BOS", "C2_NJ_PHL"])
    wx_score = st.slider("Forced weather risk score", 0, 3, 0)
    run = st.button("Run simulation", type="primary")

spec = {
    "label": "Custom scenario",
    "demand_spike_pct": demand,
    "closed_corridors": [] if closure == "(none)" else [closure],
    "driver": int(drivers),
    "truck_standard": int(std_trucks),
    "truck_temp_controlled": int(reefer_trucks),
    "weather_override": ({} if wx_corridor == "(none)" or wx_score == 0
                         else {wx_corridor: int(wx_score)}),
}


def _kpi_table(k: dict) -> pd.DataFrame:
    rows = []
    for cid, days in k.get("corridors", {}).items():
        for day, c in days.items():
            rows.append({"corridor": cid, "day": day, **c})
    return pd.DataFrame(rows)


if run:
    if offline:
        from main import _install_offline_stubs
        _install_offline_stubs()
    from graph import build_graph

    app = build_graph()
    init = {"pdf_path": DEFAULT_PDF, "csv_path": DEFAULT_CSV, "scenario_spec": spec}

    st.subheader("Agent cowork — live")
    trace_box = st.container()
    final: dict = {}
    with st.status("Agents working...", expanded=True) as status:
        for node, update in stream_graph(app, init):
            final.update({k: v for k, v in update.items()})
            summary = ""
            for ev in update.get("cowork_trace", []):
                if ev["node"] == node:
                    summary = ev["summary"]
            trace_box.markdown(
                f"**{node}** — {summary or HANDOFF.get(node, '')}  \n"
                f"<span style='color:gray;font-size:0.85em'>{HANDOFF.get(node,'')}</span>",
                unsafe_allow_html=True)
        status.update(label="Done", state="complete")

    base = final.get("baseline_kpis", {})
    scen = final.get("scenario_kpis", {})
    st.subheader("KPI impact — baseline vs scenario")
    c1, c2, c3, c4 = st.columns(4)
    bp, sp = base.get("total_penalty_score", 0), scen.get("total_penalty_score", 0)
    c1.metric("Penalty score", sp, delta=sp - bp, delta_color="inverse")
    c2.metric("Tier-1 units impacted", scen.get("tier1_units_impacted", 0))
    c3.metric("Stranded units", scen.get("stranded_units", 0))
    c4.metric("Audit iterations", final.get("audit_iterations", 0))

    bt = _kpi_table(base)
    stt = _kpi_table(scen)
    if not stt.empty:
        st.subheader("Trucks required by corridor / day (scenario)")
        fig, ax = plt.subplots(figsize=(6, 3))
        stt["lane"] = stt["corridor"] + " " + stt["day"]
        stt.set_index("lane")[["reefer_trucks_required",
                                "standard_trucks_required"]].plot.bar(ax=ax)
        ax.set_ylabel("trucks")
        st.pyplot(fig)

    colA, colB = st.columns(2)
    with colA:
        st.subheader("Impact analysis")
        st.write(final.get("impact_analysis", "(n/a)"))
        st.subheader("Audit result")
        st.code(final.get("audit_result", "(n/a)"))
    with colB:
        st.subheader("Contingency plan")
        st.write(final.get("contingency_plan", "(n/a)"))

    st.subheader("Executive report")
    st.html(final.get("report_html", "<p>(no report)</p>"))
    with st.expander("Excluded shipments (data-quality)"):
        st.text(final.get("excluded_md", "(none)"))
else:
    st.info("Configure a scenario in the sidebar and click **Run simulation**.")
