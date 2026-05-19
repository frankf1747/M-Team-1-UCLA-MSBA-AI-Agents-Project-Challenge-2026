"""End-to-end graph smoke test with the LLM/RAG layer stubbed (no network)."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


def test_graph_runs_end_to_end_and_loops(monkeypatch):
    import graph

    class _FakeRag:
        def __init__(self, *a, **k): pass
        def build(self, *a, **k): return None
        def retriever(self, *a, **k):
            return type("R", (), {"invoke": lambda self, q: []})()

    monkeypatch.setattr(graph, "PdfRag", _FakeRag)
    monkeypatch.setattr(graph, "run_context_agent", lambda *_: "rules")
    monkeypatch.setattr(graph, "run_impact_agent", lambda *a, **k: "impact")
    monkeypatch.setattr(graph, "run_contingency_agent", lambda *a, **k: "plan")

    calls = {"n": 0}

    def _audit(*a, **k):
        calls["n"] += 1
        return ("verdict\nCOMPLIANT: no", False) if calls["n"] == 1 \
            else ("verdict\nCOMPLIANT: yes", True)

    monkeypatch.setattr(graph, "run_audit_agent", _audit)
    monkeypatch.setattr(graph, "run_report_agent", lambda **k: "<h1>report</h1>")

    app = graph.build_graph()
    final = app.invoke({
        "pdf_path": "data/SeeWeeS Specialty distribution.pdf",
        "csv_path": "data-augmented/incoming_shipments_scenario.csv",
        "scenario_spec": {"label": "smoke", "demand_spike_pct": 20,
                          "closed_corridors": [], "driver": 6,
                          "truck_standard": 4, "truck_temp_controlled": 2,
                          "weather_override": {}},
    })

    assert final["report_html"] == "<h1>report</h1>"
    assert final["audit_iterations"] == 2            # loop fired once
    assert final["audit_compliant"] is True
    assert final["scenario_kpis"]["total_penalty_score"] > 0
    assert final["baseline_kpis"]["total_penalty_score"] == 0
    nodes = [e["node"] for e in final["cowork_trace"]]
    assert nodes.count("contingency_planner") == 2   # re-planned after audit
