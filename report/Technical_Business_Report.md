# SeeWeeS What-if Scenario Simulation
### Technical & Business Documentation — UCLA MSBA AI Agents Project Challenge 2026
**Focus #2: "What-if" Scenario Simulation**

---

## 1. Executive Summary

**Stakeholder:** SeeWeeS VP of Supply Chain Operations.

**Operational pain point.** SeeWeeS ships time-critical medicine (oncology
biologics, insulin, antivirals) on a 48-hour planning horizon across two
delivery corridors (NJ→Boston on I-95, NJ→Philadelphia). The original Ops
Reporting Agent is a single linear pass: it tells leadership *what is happening
now*. It cannot answer the questions that actually keep an operations VP awake:
*"What if oncology demand spikes 20%? What if we lose a reefer truck and two
drivers? What if a storm hits I-95?"* Those decisions are made under time
pressure, with patient outcomes and cold-chain integrity at stake, and today
they are made on gut feel.

**What we built.** A multi-agent **what-if decision sandbox**. The user
specifies a hypothetical disruption; deterministic engines recompute the
fleet plan and the playbook's penalty score; LLM agents explain the impact,
draft a contingency plan, and a compliance **audit agent loops the plan back
for correction** until it is safe — before any report reaches leadership.

**Headline result (augmented 48h feed, baseline penalty = 0):**

| Scenario | Total penalty score | Tier-1 units impacted | Read |
|---|---:|---:|---|
| Baseline | 0 | 0 | Fleet is feasible as planned |
| Demand spike +20% | **4,040** | 18 | Reefer fleet is the binding constraint |
| Corridor closure (Philadelphia) | **1,440** | 0 | 36 Tier-2 units stranded, none life-critical |
| Driver + reefer shortage | **2,800** | 10 | Drivers become the bottleneck, not trucks |
| Weather surge on I-95 | **1,080** | — | +40% travel buffer eats reefer capacity |

The dollar-free penalty score makes corridor trade-offs explicit and gradable,
exactly as the playbook §13.2 intends.

---

## 2. Key Assumptions

1. **Corridor → SLA tier.** C1 (I-95/Boston) carries Tier-1 life-critical
   demand (6h SLA); C2 (Philadelphia) is Tier-2 standard specialty (12h).
   Encoded in `data-augmented/corridor_sla.csv`.
2. **Penalty model used verbatim** from playbook §13.2 (Tier-1 SLA = 100,
   Tier-2 = 40, cold-chain = +80 additive, non-SLA delay = 10). No
   team-proposed re-weighting, to keep results comparable and gradable.
3. **Resource file is authoritative** for daily availability (playbook §13.1);
   we read Day0 availability (6 drivers, 4 standard, 2 reefer trucks).
4. **One driver per truck** — a truck with no driver cannot dispatch.
5. **Corridor closure strands demand, it does not delete it.** Closed-corridor
   units are flagged undeliverable and penalized (playbook §12 exception
   handling), rather than silently disappearing.
6. **Weather override is a planning lever**, mapped to the playbook §5.2 travel
   buffer (risk 1/2/3 → +10/25/40% effective transit), not a live forecast.
7. **Augmented shipment feed.** The provided 14-day file has only ~33
   planning-window rows, too small to stress a 2-reefer/4-truck fleet. Per the
   PDF's explicit invitation to "simulate realistic values," we generated a
   deterministic 72-row 48h feed sized so baseline is feasible and each
   disruption clearly bites.

---

## 3. Technical Methodology

### 3.1 Architectural enhancements (LangGraph)

The original graph was strictly linear. The new graph adds reconciliation,
deterministic simulation, three new reasoning agents, and a **cyclic
conditional edge**:

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
                                                            │             │ COMPLIANT: no
                                                          audit ──────────┘ (max 2 iters)
                                                            │ COMPLIANT: yes / max iters
                                                            ▼
                                                        report ─► email (optional)
```

- **New nodes:** `data_reconciliation`, `baseline_kpis`, `scenario_parser`,
  `disruption_engine`, `impact_analysis`, `contingency_planner`, `audit`.
- **Conditional cyclic edge:** `route_after_audit` sends a non-compliant plan
  back to `contingency_planner` with the audit feedback embedded, capped at 2
  iterations so the system always terminates. This is the "non-trivial logic"
  that prevents bad information reaching leadership.
- **Agent-cowork trace:** every node appends a hand-off summary to
  `cowork_trace`, streamed live to the UI so you can watch the agents pass
  information (and watch the loop fire).

### 3.2 Agent & tool design

| Component | Type | Grounding |
|---|---|---|
| `kpi_engine.py` | deterministic tool | Playbook §8 capacity model + §13.2 penalty model |
| `scenario_engine.py` | deterministic tool | Applies demand/closure/shortage/weather levers |
| `csv_tools.reconcile_shipments` | deterministic tool | DQ-01..04 + Appendix A precedence (exact→alias→legacy) |
| ImpactAnalysisAgent | LLM | Interprets engine deltas only — forbidden from inventing numbers |
| ContingencyPlannerAgent | LLM | Constrained to playbook §13 allocation policy |
| AuditAgent | LLM | Emits a parseable `COMPLIANT: yes/no` verdict |
| ReportAgent | LLM | Executive HTML, decision-first |

Separating *math* (deterministic, tested) from *judgement* (LLM) is what makes
the impact numbers defensible.

### 3.3 Data augmentation strategy

- **Item master reconciliation tables** (Appendix A.1/A.2/A.3 encoded as CSV)
  so the OpsData layer resolves missing/legacy/alias identifiers to a stable
  `canonical_item_id` with a logged reason code.
- **`corridor_sla.csv`** — defines SLA tier + hospital priority (a "missing
  link" the raw data lacks).
- **`incoming_shipments_scenario.csv`** — realistic 48h feed
  (`make_scenario_dataset.py`, deterministic and reproducible).

---

## 4. Results & Validation

### 4.1 Business insight (example: driver + reefer shortage)

Cutting the pool to 3 drivers and 1 reefer truck produces a **2,800 penalty
with 10 Tier-1 units impacted**. The impact agent identifies that **drivers,
not trucks, are the binding constraint** here — a counter-intuitive but
actionable finding: leadership should pull a driver from standby before leasing
a reefer. The contingency agent's first plan was rejected by the audit agent
("Tier-1 units stranded without escalation"); after the loop it returned a
compliant plan that escalates Tier-1 and defers Tier-2 within SLA. Leadership
only ever sees the corrected plan.

### 4.2 Validation strategy

- **Deterministic engines are unit-tested** against hand-computed truck counts
  and penalty scores (`test_kpi_engine.py`, `test_scenario_engine.py`,
  `test_reconciliation.py`) — these are the ground truth.
- **End-to-end smoke test** (`test_smoke.py`) mocks the LLM layer and asserts
  the graph completes, the audit loop fires exactly once, and
  `audit_iterations == 2`. All 9 tests pass.
- **Cross-scenario sanity:** baseline = 0, every disruption > 0 and distinct,
  confirming each lever maps to a different binding constraint.

### 4.3 How to reproduce

```bash
cd app && pip install -r requirements.txt
python -m src.main --preset demand_spike_20 --no-llm   # deterministic
streamlit run src/streamlit_app.py                     # interactive
python -m pytest tests/ -q
```

---

## 5. Limitations & Next Steps

- **No true optimizer.** The contingency agent reasons over engine output; it
  does not solve for the provably minimum-penalty allocation. Next step: add a
  greedy/LP allocator and let the agent critique its output.
- **Demand spike is a uniform resample.** A real spike is product- and
  hospital-specific; with real demand signals we would scale per item class.
- **Weather is a manual override.** Production would pull the live Open-Meteo
  per-waypoint forecast (the tool already exists) and auto-set the score.
- **Two corridors, 48h.** The engine generalizes to N corridors / longer
  horizons; the scenario feed and resource file would simply grow.
- **LLM variance.** Numbers are deterministic, but narrative wording varies;
  the audit gate constrains *safety*, not prose. A rubric-based second auditor
  could tighten consistency.

With real-time demand, telematics, and weather feeds, this same graph becomes a
standing operations co-pilot rather than a what-if sandbox.
