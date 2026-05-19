# SeeWeeS Scenario Simulation (UCLA MSBA AI Agents Challenge 2026)

**Core Focuses: #2 What-if Scenario Simulation + #1 Self-Correcting Compliance Audit.**
This project turns the linear SeeWeeS Ops Reporting Agent into a **multi-agent
decision sandbox** that combines two complementary capabilities:

- **#2 — What-if Scenario Simulation.** A user specifies hypothetical disruptions
  (demand spike, warehouse / corridor closure, driver / truck shortage, weather
  surge); deterministic engines simulate the impact on KPIs using the SeeWeeS
  playbook's own capacity and penalty models.
- **#1 — Self-Correcting Compliance Audit.** Before any plan reaches leadership,
  a compliance audit agent reviews it against the playbook (SLA tiers,
  cold-chain rules, escalation triggers, resource ceilings). Non-compliant
  plans are looped back to the planner with feedback until they are safe —
  the system never publishes a plan it considers non-compliant.

Together they produce an executive-ready contingency plan that is both
quantitatively grounded and rule-checked.

> Not just *"what is happening"* — also *"if it goes wrong, what do we do?"*

---

## What's in here

```
.
├── README.md                     ← you are here (deployment guide)
├── docs/superpowers/             ← design spec + implementation plan
├── report/
│   └── Technical_Business_Report.docx   ← graded business & technical write-up
└── app/
    ├── README.md                 ← app run notes
    ├── requirements.txt  .env.example
    ├── data/                     ← original PDF + CSV (unchanged)
    ├── data-for-enhancement/     ← provided playbook + multi-corridor + resources
    ├── data-augmented/           ← OUR augmented datasets + scenario presets
    └── src/
        ├── graph.py              ← LangGraph flow (cyclic audit loop)
        ├── state.py  prompts.py  agents.py
        ├── main.py               ← CLI runner
        ├── web/                  ← FastAPI server + clean HTML/CSS/JS UI
        ├── tools/                ← kpi_engine, scenario_engine, reconciliation,
        │                            pdf/weather/email tools
        └── viz/cowork_trace.py   ← agent hand-off labels
```

## The multi-agent flow

```
pdf_context ─► data_reconciliation ─► baseline_kpis ─► scenario_parser
                                                            │
                                                            ▼
                                                     disruption_engine
                                                            │
                                                            ▼
                                                     impact_analysis
                                                            │
                                                            ▼
                                                   contingency_planner ◄──┐
                                                            │             │ loop if
                                                            ▼             │ NON-COMPLIANT
                                                          audit ──────────┘ (max 2x)
                                                            │ compliant / max iters
                                                            ▼
                                                        report ─► email (optional)
```

- **Deterministic engines** (`kpi_engine.py`, `scenario_engine.py`) do the math
  using the playbook's capacity model (§8) and penalty model (§13.2:
  Tier1=100, Tier2=40, cold-chain +80, delay 10) — so impact numbers are
  defensible, not LLM guesses.
- **LLM agents** (impact / contingency / audit / report) explain, recommend,
  and self-correct.
- The **audit → contingency_planner cycle** is the "non-trivial logic": a
  non-compliant plan is sent back with feedback before leadership ever sees it.

## Setup

```bash
cd app
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # add OPENAI_API_KEY for live LLM runs
```

## Run it

**Web UI (recommended):**
```bash
cd app
uvicorn web.server:app --app-dir src --port 8000
# then open http://localhost:8000
```
A clean clinical-style single-page app: build a scenario in the left panel →
**Run simulation** → watch the agent-cowork flow animate the information
hand-off (and the audit loop firing), then read the baseline-vs-scenario KPIs
and the executive report. Runs **offline/deterministic** automatically when no
`OPENAI_API_KEY` is set; set the key for live LLM narration.

**Command line (reproducible, for graders):**
```bash
cd app
# offline, deterministic — no API key needed
python -m src.main --preset demand_spike_20 --no-llm
# live LLM run
python -m src.main --preset driver_shortage
```
Presets: `baseline`, `demand_spike_20`, `corridor_closure`,
`driver_shortage`, `storm_i95` (see `app/data-augmented/scenario_presets.json`).

## Tests

```bash
cd app && python -m pytest tests/ -q
```
The deterministic engines are unit-tested against hand-computed truck counts
and penalty scores; a mocked end-to-end smoke test verifies the graph wiring
and the audit loop.

## Documentation

- Design spec: `docs/superpowers/specs/2026-05-19-whatif-scenario-simulation-design.md`
- Implementation plan: `docs/superpowers/plans/2026-05-19-whatif-scenario-simulation.md`
- **Business & technical report:** `report/Technical_Business_Report.docx`
