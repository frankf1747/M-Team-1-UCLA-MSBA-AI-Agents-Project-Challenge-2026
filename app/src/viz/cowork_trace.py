"""Stream a compiled LangGraph app node-by-node so the UI can show agents
handing work to each other in real time."""
from __future__ import annotations
from typing import Iterator, Tuple, Dict, Any


def stream_graph(app, state: Dict[str, Any]) -> Iterator[Tuple[str, Dict[str, Any]]]:
    """Yield (node_name, state_update) as each node completes."""
    for chunk in app.stream(state, stream_mode="updates"):
        for node_name, update in chunk.items():
            yield node_name, (update or {})


HANDOFF = {
    "pdf_context": "Playbook rules + KPI thresholds -> downstream agents",
    "data_reconciliation": "Clean valid units + excluded log -> KPI engine",
    "baseline_kpis": "Baseline penalty/KPIs -> impact comparison",
    "scenario_parser": "Structured ScenarioSpec -> disruption engine",
    "disruption_engine": "Scenario KPIs -> impact analysis",
    "impact_analysis": "Quantified deltas + binding constraint -> planner",
    "contingency_planner": "Draft contingency plan -> audit",
    "audit": "Compliance verdict -> loop back or report",
    "report": "Executive HTML report -> leadership",
    "email": "Optional email dispatch",
}
