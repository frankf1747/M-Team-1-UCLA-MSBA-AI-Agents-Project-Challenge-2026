"""FastAPI server for the SeeWeeS What-if Scenario Simulation.

Run from the app/ directory:
    uvicorn src.web.server:app --reload --port 8000
then open http://localhost:8000
"""
from __future__ import annotations
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ""))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

import json

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
DEFAULT_CSV = "data-augmented/incoming_shipments_scenario.csv"
DEFAULT_PDF = "data/SeeWeeS Specialty distribution.pdf"

# Offline (deterministic, no API key) unless a real key is present.
OFFLINE = not os.getenv("OPENAI_API_KEY", "").strip()

app = FastAPI(title="SeeWeeS What-if Simulation")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

_graph_app = None


def _get_app():
    global _graph_app
    if _graph_app is None:
        if OFFLINE:
            from main import _install_offline_stubs
            _install_offline_stubs()
        from graph import build_graph
        _graph_app = build_graph()
    return _graph_app


def _spec(demand_spike_pct, closed_corridors, driver, truck_standard,
          truck_temp_controlled, weather_corridor, weather_score, label):
    wx = ({} if not weather_corridor or weather_score == 0
          else {weather_corridor: int(weather_score)})
    return {
        "label": label,
        "demand_spike_pct": demand_spike_pct,
        "closed_corridors": closed_corridors,
        "driver": driver,
        "truck_standard": truck_standard,
        "truck_temp_controlled": truck_temp_controlled,
        "weather_override": wx,
    }


def _payload(final: dict) -> dict:
    return {
        "offline": OFFLINE,
        "cowork_trace": final.get("cowork_trace", []),
        "baseline_kpis": final.get("baseline_kpis", {}),
        "scenario_kpis": final.get("scenario_kpis", {}),
        "impact_analysis": final.get("impact_analysis", ""),
        "contingency_plan": final.get("contingency_plan", ""),
        "audit_result": final.get("audit_result", ""),
        "audit_iterations": final.get("audit_iterations", 0),
        "audit_compliant": final.get("audit_compliant", False),
        "excluded_md": final.get("excluded_md", ""),
        "report_html": final.get("report_html", ""),
    }


class ScenarioIn(BaseModel):
    demand_spike_pct: float = 0
    closed_corridors: list[str] = []
    driver: int = 6
    truck_standard: int = 4
    truck_temp_controlled: int = 2
    weather_corridor: str = ""
    weather_score: int = 0
    label: str = "Custom scenario"


@app.get("/", response_class=HTMLResponse)
def index():
    with open(os.path.join(STATIC_DIR, "index.html")) as f:
        return f.read()


@app.get("/api/meta")
def meta():
    return {"offline": OFFLINE}


@app.post("/api/run")
def run(scenario: ScenarioIn):
    spec = _spec(scenario.demand_spike_pct, scenario.closed_corridors,
                 scenario.driver, scenario.truck_standard,
                 scenario.truck_temp_controlled, scenario.weather_corridor,
                 scenario.weather_score, scenario.label)
    final = _get_app().invoke({
        "pdf_path": DEFAULT_PDF, "csv_path": DEFAULT_CSV, "scenario_spec": spec,
    })
    return JSONResponse(_payload(final))


@app.get("/api/run/stream")
def run_stream(demand_spike_pct: float = 0, closed: str = "", driver: int = 6,
               truck_standard: int = 4, truck_temp_controlled: int = 2,
               weather_corridor: str = "", weather_score: int = 0):
    """Server-Sent Events: one `node` event per agent as it completes, then
    a final `done` event with the full result payload."""
    from viz.cowork_trace import stream_graph
    closed_list = [c for c in closed.split(",") if c]
    spec = _spec(demand_spike_pct, closed_list, driver, truck_standard,
                 truck_temp_controlled, weather_corridor, weather_score,
                 "Custom scenario")
    graph_app = _get_app()
    init = {"pdf_path": DEFAULT_PDF, "csv_path": DEFAULT_CSV,
            "scenario_spec": spec}

    def gen():
        final: dict = {}
        for node, update in stream_graph(graph_app, init):
            final.update(update)
            if node == "email":  # no UI chip; nothing to show
                continue
            trace = update.get("cowork_trace", [])
            summary = trace[-1]["summary"] if trace else ""
            yield ("event: node\ndata: "
                   + json.dumps({"node": node, "summary": summary}) + "\n\n")
        yield "event: done\ndata: " + json.dumps(_payload(final)) + "\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream")
