"""CLI runner for the SeeWeeS What-if Scenario Simulation.

Examples:
  python -m src.main --preset demand_spike_20
  python -m src.main --scenario data-augmented/scenario_presets.json --preset driver_shortage
  python -m src.main --preset corridor_closure --no-llm   # offline, deterministic only
"""
from __future__ import annotations
import argparse
import json
import os
import sys

from dotenv import load_dotenv

load_dotenv()

DEFAULT_PRESETS = "data-augmented/scenario_presets.json"
DEFAULT_PDF = "data/SeeWeeS Specialty distribution.pdf"
DEFAULT_CSV = "data-augmented/incoming_shipments_scenario.csv"


def _install_offline_stubs() -> None:
    """Replace LLM/RAG calls with deterministic stubs so the engine runs with no API key."""
    import graph

    class _FakeRag:
        def __init__(self, *a, **k): pass
        def build(self, *a, **k): return None
        def retriever(self, *a, **k):
            return type("R", (), {"invoke": lambda self, q: []})()

    graph.PdfRag = _FakeRag
    graph.run_context_agent = lambda *_: "[offline] Playbook rules loaded (stub)."
    graph.run_impact_agent = lambda label, b, s, **k: (
        f"[offline] Penalty moved {b.get('total_penalty_score')} -> "
        f"{s.get('total_penalty_score')} for scenario '{label}'.")
    graph.run_contingency_agent = lambda *a, **k: (
        "[offline] 1) Reallocate reefer trucks to Tier 1 corridor. "
        "2) Prioritize cold-chain. 3) Defer Tier 2 within SLA.")
    # First audit fails, second passes -> exercises the cyclic loop offline.
    _state = {"n": 0}

    def _fake_audit(*a, **k):
        _state["n"] += 1
        if _state["n"] == 1:
            return ("Tier 1 units stranded without escalation.\nCOMPLIANT: no", False)
        return ("Escalation now present.\nCOMPLIANT: yes", True)

    graph.run_audit_agent = _fake_audit
    graph.run_report_agent = lambda **k: (
        f"<h1>SeeWeeS What-if Report — {k.get('scenario_label')}</h1>"
        f"<p>{k.get('impact_analysis')}</p><pre>{k.get('contingency_plan')}</pre>")


def main() -> None:
    p = argparse.ArgumentParser(description="SeeWeeS What-if Scenario Simulation")
    p.add_argument("--scenario", default=DEFAULT_PRESETS, help="path to scenario presets JSON")
    p.add_argument("--preset", default="demand_spike_20", help="preset key to run")
    p.add_argument("--pdf", default=DEFAULT_PDF)
    p.add_argument("--csv", default=DEFAULT_CSV)
    p.add_argument("--no-llm", action="store_true", help="offline deterministic run (no API key)")
    args = p.parse_args()

    sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

    with open(args.scenario) as f:
        presets = json.load(f)
    if args.preset not in presets:
        raise SystemExit(f"Unknown preset '{args.preset}'. Options: {list(presets)}")
    spec = presets[args.preset]

    if args.no_llm:
        _install_offline_stubs()

    from graph import build_graph
    app = build_graph()

    final = app.invoke({
        "pdf_path": args.pdf,
        "csv_path": args.csv,
        "scenario_spec": spec,
    })

    base = final.get("baseline_kpis", {})
    scen = final.get("scenario_kpis", {})
    print(f"\n=== SCENARIO: {spec.get('label')} ===")
    print(f"Baseline penalty score : {base.get('total_penalty_score')}")
    print(f"Scenario penalty score : {scen.get('total_penalty_score')}")
    print(f"Tier-1 units impacted  : {scen.get('tier1_units_impacted')}")
    print(f"Audit iterations       : {final.get('audit_iterations')}  "
          f"(compliant={final.get('audit_compliant')})")
    print("\n--- Agent cowork trace ---")
    for ev in final.get("cowork_trace", []):
        print(f"  [{ev['node']}] {ev['summary']}")
    print("\n--- Report (first 1500 chars) ---")
    print((final.get("report_html") or "")[:1500])


if __name__ == "__main__":
    main()
