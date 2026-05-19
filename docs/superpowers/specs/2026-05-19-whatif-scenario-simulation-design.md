# What-if Scenario Simulation — Design Spec

**Date:** 2026-05-19
**Assignment:** UCLA MSBA AI Agents Project Challenge 2026 — Focus #2 ("What-if" Scenario Simulation)
**Status:** Approved by user, ready for implementation planning

---

## 1. Problem & Stakeholder

**Stakeholder:** SeeWeeS VP of Supply Chain Operations.

**Operational pain point:** The current SeeWeeS Ops Reporting Agent is a *linear* pipeline
(`pdf_context → csv_analysis → weather → planner → report → email`). It only reports *what is
happening now*. It cannot answer *"what if"* questions before the 48-hour planning window
starts — e.g. "what happens to on-time delivery and cost if oncology demand spikes 20% while
we lose a reefer truck and I-95 gets a storm?"

**Goal:** Transform the prototype into a multi-agent **what-if decision sandbox** that lets a user
specify hypothetical disruptions, simulates the quantitative impact on KPIs using the SeeWeeS
playbook's own models, and produces grounded, executive-ready contingency recommendations —
with a cyclic self-correcting audit loop so leadership never receives a non-compliant plan.

## 2. Scope

**In scope** — four disruption levers (the three named in the PDF + weather, which plugs into
existing logic):

1. **Demand spike** — scale shipment volume by `+X%` (optionally per corridor).
2. **Warehouse / corridor closure** — remove a corridor (`C1_I95_NJ_BOS` or `C2_NJ_PHL`) or
   origin DC from the planning window.
3. **Driver / truck shortage** — reduce `driver`, `truck_standard`, or `truck_temp_controlled`
   counts from `Resource_availability_48h.csv`.
4. **Weather risk override** — force a corridor's `risk_score_0_3` upward (storm scenario),
   feeding the playbook's existing travel-buffer + escalation rules.

Scenarios can be combined in one run and are compared against the unmodified baseline.

**Out of scope (YAGNI):** linear/MILP optimizer or solver, authentication, databases,
multi-day horizon beyond the playbook's 48h, real email sending (kept off by default),
custom natural-language scenario parsing (UI provides structured input).

## 3. Architecture

### 3.1 LangGraph flow (new)

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
                                                              ▼             │ non-compliant
                                                            audit ──────────┘ (max 2 iters)
                                                              │ compliant / max iters
                                                              ▼
                                                          report ─► email (optional, off)
```

Conditional edge from `audit`: `→ contingency_planner` while `(not compliant) and (iterations < 2)`,
else `→ report`. This cycle is the assignment's required "non-trivial logic."

### 3.2 Nodes

| Node | Type | Responsibility |
|---|---|---|
| `pdf_context` | LLM (existing ContextAgent) | Extract KPI defs, SLA tiers, thresholds, dispatch rules from playbook PDF (RAG). |
| `data_reconciliation` | deterministic tool | Load 14-day multi-corridor CSV; apply DQ-01..04 + Appendix A (canonical IDs, legacy map, alias). Emit cleaned valid units + excluded log with reason codes. |
| `baseline_kpis` | deterministic tool | Compute baseline KPIs over the 48h window: volume by corridor, Tier1/Tier2 mix, trucks-required, resource gap, SLA risk, total penalty score. |
| `scenario_parser` | deterministic | Validate/normalize the structured `ScenarioSpec` from the UI/CLI into the engine's input contract. |
| `disruption_engine` | deterministic tool | Apply scenario transforms to reconciled data + resource pool; recompute the same KPI set under disruption. |
| `impact_analysis` | LLM (ImpactAnalysisAgent) | Compare baseline vs scenario KPI tables; explain deltas, root causes, binding constraint. |
| `contingency_planner` | LLM (ContingencyPlannerAgent) | Propose mitigations grounded in playbook §13 allocation policy (prioritize Tier1, reallocate reefers, defer Tier2 within SLA). Structured output. |
| `audit` | LLM + deterministic checks (AuditAgent) | Re-score the proposed plan; validate vs SLA tiers, cold-chain, risk-score-3 escalation. If violated → loop back with feedback. |
| `report` | LLM (ReportAgent) | Executive HTML: summary, baseline-vs-scenario KPI table, penalty breakdown, top risks, concrete actions, "why". |
| `email` | deterministic (existing) | Optional SMTP send; disabled unless `REPORT_EMAIL_TO` set. |

### 3.3 State schema (`state.py`)

Extends current `AppState` (TypedDict, `total=False`) with:
`reconciliation` (valid units df-as-records, excluded log), `baseline_kpis`,
`scenario_spec`, `scenario_kpis`, `impact_analysis`, `contingency_plan`,
`audit_result`, `audit_iterations`, `cowork_trace` (list of node events for UI).

## 4. Deterministic Models (grounded in playbook)

### 4.1 Capacity model (playbook §8)
- 1 `unique_item_id` = 1 volume unit; standard truck capacity = 10 units.
- `required_trucks = ceil(total_volume * 1.10 / 10)`, computed per corridor per day.
- Cold-chain items (temp_control ∈ {Cold, Strict Cold Chain}) require temp-controlled trucks.

### 4.2 Penalty model (playbook §13.2) — the gradable objective
Per affected unit: Tier1 SLA violation = 100; Tier2 SLA violation = 40;
cold-chain violation = +80 (additive); non-SLA delivery delay = 10.
**Total penalty score** = sum over all impacted units, both days, all corridors.
Tie-break: prefer fewer Tier1 units impacted.

### 4.3 KPI set
- Shipment volume by corridor & day
- Tier1 / Tier2 mix
- Valid vs excluded unit counts (+ reason codes)
- Trucks required vs available (standard & temp-controlled) → gap
- Driver requirement vs available → gap
- SLA-at-risk unit count
- **Total penalty score** (headline KPI)

### 4.4 SLA mapping assumption
Corridor `default_sla_tier` (C1 = Tier 1, C2 = Tier 2) sets the unit's SLA tier unless the
medicine is life-critical. Documented as a key assumption.

## 5. Data Augmentation (PDF requirement)

Created in `app/data-augmented/`:
- `item_master_canonical.csv` — Appendix A.1 encoded for the reconciliation tool.
- `item_alias.csv`, `item_legacy_map.csv` — Appendix A.2 / A.3 encoded.
- `corridor_sla.csv` — corridor → SLA tier, hospital priority assumptions.
- `scenario_presets.json` — the 3 PDF scenarios as parameterized presets.
All augmentation rationale documented in `report/Technical_Business_Report.md`.

> **Addendum (2026-05-19):** Per user request the UI was changed from Streamlit
> to a **FastAPI server + custom HTML/CSS/JS** single-page app
> (`src/web/`), clean clinical-medical style. The functional design below
> (scenario builder, KPI comparison, agent-cowork hand-off view) is unchanged;
> only the delivery layer differs. `streamlit`/`matplotlib` replaced by
> `fastapi`/`uvicorn` in requirements.

## 6. Minimalist UI (`streamlit_app.py`)

- **Sidebar — Scenario Builder:** demand-spike slider (%), corridor/DC closure dropdown,
  driver/standard/reefer truck number inputs, weather-override (corridor + forced score), Run button.
- **Main:** baseline-vs-scenario KPI cards with deltas; per-corridor bar chart;
  penalty breakdown bar; contingency recommendations; rendered exec HTML report.
- **Agent Cowork panel:** consumes `graph.stream()` events via `viz/cowork_trace.py`;
  each node shows pending → running → done with a one-line "passed downstream: …" hand-off;
  audit-loop iteration count visibly increments when the back-edge fires.
- Default Streamlit theme (minimalist), no custom CSS.

## 7. Reproducibility

- `app/main.py` runs the same compiled graph headlessly:
  `python -m src.main --scenario data-augmented/scenario_presets.json --preset demand_spike_20`
- `requirements.txt` adds `streamlit`, `tabulate` (markdown tables), `matplotlib` (charts).
- `.env.example` updated; no secrets committed.

## 8. Testing / Validation Strategy

- `tests/test_kpi_engine.py` — fixed input rows → asserted truck counts & penalty score.
- `tests/test_scenario_engine.py` — demand +20% / closure / shortage produce expected KPI deltas.
- `tests/test_smoke.py` — graph compiles and runs end-to-end on a tiny fixture with the LLM
  layer monkeypatched (no network).
- Validation narrative in the report cites these deterministic checks as ground truth.

## 9. Deliverables Mapping (PDF)

| PDF requirement | Where |
|---|---|
| Source code (graph/prompts/agents) | `app/src/` |
| Augmented dataset | `app/data-augmented/` |
| requirements.txt + .env.example | `app/` |
| README deployment guide | `README.md` (root) + `app/README.md` |
| Technical & Business report | `report/Technical_Business_Report.md` |
| Architecture enhancements writeup | report §Technical methodology |
| Results & validation | report §Results (UI screenshots/logs) + tests |
| Limitations & next steps | report final section |

## 10. Key Assumptions

1. Corridor default SLA tier governs unit SLA unless life-critical (documented).
2. Weather override is a planning lever, not a real forecast call, in scenario mode.
3. Hospital priority levels simulated in `corridor_sla.csv` (no real source available).
4. Resource file is authoritative for daily availability (per playbook §13.1).
5. Penalty model used verbatim from playbook §13.2 (no team-proposed adjustment).
