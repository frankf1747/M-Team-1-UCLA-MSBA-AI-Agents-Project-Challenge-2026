from __future__ import annotations
import os
import time
from typing import Dict, Any

import pandas as pd
from langgraph.graph import StateGraph, END
from dotenv import load_dotenv

from state import AppState
from tools.pdf_tools import PdfRag
from tools.csv_tools import reconcile_shipments
from tools.kpi_engine import compute_kpis, ResourcePool
from tools.scenario_engine import ScenarioSpec, apply_scenario
from agents import (
    run_context_agent, run_impact_agent, run_contingency_agent,
    run_audit_agent, run_report_agent,
)

load_dotenv()

MAX_AUDIT_ITERS = 2
DATA_AUGMENTED = os.getenv("DATA_AUGMENTED_DIR", "data-augmented")


def _trace(state: AppState, node: str, summary: str) -> list:
    trace = list(state.get("cowork_trace", []))
    trace.append({"node": node, "summary": summary, "ts": round(time.time(), 3)})
    return trace


def _load_resource_pool() -> ResourcePool:
    path = os.path.join("data-for-enhancement", "Resource_availability_48h.csv")
    df = pd.read_csv(path)
    day0 = df[df["day"] == "Day0"].set_index("resource_type")["available_count"]
    return ResourcePool(
        driver=int(day0.get("driver", 6)),
        truck_standard=int(day0.get("truck_standard", 4)),
        truck_temp_controlled=int(day0.get("truck_temp_controlled", 2)),
    )


def _attach_sla(units: pd.DataFrame) -> pd.DataFrame:
    sla = pd.read_csv(os.path.join(DATA_AUGMENTED, "corridor_sla.csv"))
    sla_map = dict(zip(sla["corridor_id"], sla["sla_tier"]))
    units = units.copy()
    units["sla_tier"] = units["corridor_id"].map(sla_map).fillna(2).astype(int)
    return units


# ---------- nodes ----------

def node_pdf_context(state: AppState) -> AppState:
    rag = PdfRag(persist_dir="chroma_db")
    vectordb = rag.build(state["pdf_path"])
    docs = rag.retriever(vectordb, k=6).invoke(
        "Extract KPI definitions, thresholds, SLAs, constraints, dispatch rules, exceptions."
    )
    snippets = "\n\n---\n\n".join(d.page_content for d in docs)
    ctx = run_context_agent(snippets)
    return {"business_context": ctx,
            "cowork_trace": _trace(state, "pdf_context",
                                   "Extracted playbook rules/KPIs/thresholds")}


def node_data_reconciliation(state: AppState) -> AppState:
    df = pd.read_csv(state["csv_path"])
    if "is_planning_window" in df.columns:
        df = df[df["is_planning_window"] == 1].copy()
    res = reconcile_shipments(df, master_dir=DATA_AUGMENTED)
    valid = _attach_sla(res["valid"])
    excluded = res["excluded"]
    excluded_md = (excluded[["item_id", "item_name", "reason"]].head(15).to_markdown(index=False)
                   if not excluded.empty else "(no excluded shipments)")
    return {
        "_valid_units": valid.to_dict("records"),
        "reconciliation_stats": res["stats"],
        "excluded_md": excluded_md,
        "cowork_trace": _trace(state, "data_reconciliation",
                               f"{res['stats']['valid_rows']} valid / "
                               f"{res['stats']['excluded_rows']} excluded units"),
    }


def node_baseline_kpis(state: AppState) -> AppState:
    units = pd.DataFrame(state["_valid_units"])
    pool = _load_resource_pool()
    kpis = compute_kpis(units, pool)
    return {"baseline_kpis": kpis, "_pool": pool.__dict__,
            "cowork_trace": _trace(state, "baseline_kpis",
                                   f"Baseline penalty={kpis['total_penalty_score']}")}


def node_scenario_parser(state: AppState) -> AppState:
    spec_dict = state.get("scenario_spec", {}) or {}
    spec = ScenarioSpec.from_preset(spec_dict)
    return {"_spec": spec.__dict__, "scenario_spec": spec.__dict__,
            "cowork_trace": _trace(state, "scenario_parser",
                                   f"Scenario: {spec.label}")}


def node_disruption_engine(state: AppState) -> AppState:
    units = pd.DataFrame(state["_valid_units"])
    pool = ResourcePool(**state["_pool"])
    spec = ScenarioSpec(**state["_spec"])
    s_units, s_pool = apply_scenario(units, pool, spec)
    kpis = compute_kpis(s_units, s_pool)
    return {"scenario_kpis": kpis,
            "cowork_trace": _trace(state, "disruption_engine",
                                   f"Scenario penalty={kpis['total_penalty_score']} "
                                   f"({len(s_units)} units)")}


def node_impact_analysis(state: AppState) -> AppState:
    spec = ScenarioSpec(**state["_spec"])
    txt = run_impact_agent(spec.label, state["baseline_kpis"], state["scenario_kpis"])
    return {"impact_analysis": txt,
            "cowork_trace": _trace(state, "impact_analysis",
                                   "Quantified baseline vs scenario deltas")}


def node_contingency_planner(state: AppState) -> AppState:
    feedback = ""
    if not state.get("audit_compliant", True) and state.get("audit_result"):
        feedback = state["audit_result"]
    plan = run_contingency_agent(
        state.get("business_context", ""), state.get("impact_analysis", ""),
        state["scenario_kpis"], audit_feedback=feedback,
    )
    it = state.get("audit_iterations", 0)
    return {"contingency_plan": plan,
            "cowork_trace": _trace(state, "contingency_planner",
                                   f"Drafted contingency plan (attempt {it + 1})")}


def node_audit(state: AppState) -> AppState:
    text, compliant = run_audit_agent(
        state.get("business_context", ""), state["contingency_plan"],
        state["scenario_kpis"],
    )
    iters = state.get("audit_iterations", 0) + 1
    verdict = "COMPLIANT" if compliant else "NON-COMPLIANT -> loop back"
    return {"audit_result": text, "audit_compliant": compliant,
            "audit_iterations": iters,
            "cowork_trace": _trace(state, "audit", f"Audit #{iters}: {verdict}")}


def node_report(state: AppState) -> AppState:
    spec = ScenarioSpec(**state["_spec"])
    html = run_report_agent(
        scenario_label=spec.label,
        business_context=state.get("business_context", ""),
        baseline_kpis=state.get("baseline_kpis", {}),
        scenario_kpis=state.get("scenario_kpis", {}),
        excluded_md=state.get("excluded_md", "(none)"),
        impact_analysis=state.get("impact_analysis", ""),
        contingency_plan=state.get("contingency_plan", ""),
        audit_result=state.get("audit_result", ""),
    )
    return {"report_html": html,
            "cowork_trace": _trace(state, "report",
                                   "Generated executive HTML report")}


def node_email(state: AppState) -> AppState:
    to_email = os.getenv("REPORT_EMAIL_TO", "").strip()
    if not to_email:
        return {}
    from tools.email_tools import send_email_smtp
    send_email_smtp(subject="SeeWeeS What-if Scenario Report",
                    html_body=state["report_html"], to_email=to_email)
    return {}


def route_after_audit(state: AppState) -> str:
    if not state.get("audit_compliant", False) and \
            state.get("audit_iterations", 0) < MAX_AUDIT_ITERS:
        return "contingency_planner"
    return "report"


def build_graph():
    g = StateGraph(AppState)
    g.add_node("pdf_context", node_pdf_context)
    g.add_node("data_reconciliation", node_data_reconciliation)
    g.add_node("baseline_kpis", node_baseline_kpis)
    g.add_node("scenario_parser", node_scenario_parser)
    g.add_node("disruption_engine", node_disruption_engine)
    g.add_node("impact_analysis", node_impact_analysis)
    g.add_node("contingency_planner", node_contingency_planner)
    g.add_node("audit", node_audit)
    g.add_node("report", node_report)
    g.add_node("email", node_email)

    g.set_entry_point("pdf_context")
    g.add_edge("pdf_context", "data_reconciliation")
    g.add_edge("data_reconciliation", "baseline_kpis")
    g.add_edge("baseline_kpis", "scenario_parser")
    g.add_edge("scenario_parser", "disruption_engine")
    g.add_edge("disruption_engine", "impact_analysis")
    g.add_edge("impact_analysis", "contingency_planner")
    g.add_edge("contingency_planner", "audit")
    g.add_conditional_edges("audit", route_after_audit,
                            {"contingency_planner": "contingency_planner",
                             "report": "report"})
    g.add_edge("report", "email")
    g.add_edge("email", END)
    return g.compile()
