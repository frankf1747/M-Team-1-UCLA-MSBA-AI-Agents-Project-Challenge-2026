from __future__ import annotations
from typing import TypedDict, Dict, Any, List


class AppState(TypedDict, total=False):
    # inputs
    pdf_path: str
    csv_path: str
    scenario_spec: Dict[str, Any]

    # pdf context
    business_context: str

    # reconciliation
    reconciliation_stats: Dict[str, Any]
    excluded_md: str

    # KPIs
    baseline_kpis: Dict[str, Any]
    scenario_kpis: Dict[str, Any]

    # weather (kept for compatibility / storm override)
    weather_risk: Dict[str, Any]

    # what-if agent outputs
    impact_analysis: str
    contingency_plan: str
    audit_result: str
    audit_compliant: bool
    audit_iterations: int

    # final
    report_html: str

    # UI agent-cowork trace
    cowork_trace: List[Dict[str, Any]]

    # internal pass-through (not for display)
    _valid_units: List[Dict[str, Any]]
    _pool: Dict[str, Any]
    _spec: Dict[str, Any]
