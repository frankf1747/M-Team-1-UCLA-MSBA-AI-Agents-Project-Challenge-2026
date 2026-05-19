# What-if Scenario Simulation Implementation Plan

> **For agentic workers:** Steps use checkbox (`- [ ]`) syntax. Execute task-by-task; run verifications; commit per task.

**Goal:** Turn the linear SeeWeeS ops agent into a multi-agent what-if scenario sandbox with a cyclic audit loop, deterministic playbook-grounded KPI/penalty engine, a minimalist Streamlit UI, and an agent-cowork trace.

**Architecture:** Reorganize repo into `app/`. Add deterministic engines (`kpi_engine.py`, `scenario_engine.py`, reconciliation in `csv_tools.py`), new LangGraph nodes + cyclic edge, three new LLM agents, Streamlit UI consuming `graph.stream()`, and the graded report.

**Tech Stack:** Python 3.11, LangGraph, LangChain-OpenAI, pandas, scikit-learn, Streamlit, matplotlib, pytest.

---

### Task 1: Repo restructure into `app/`

**Files:**
- Move: `MSBA_AI_Agents_Demo-data-enhancement-seewees/*` → `app/`
- Create: `app/data-augmented/.gitkeep`, `docs/`, `report/`

- [ ] **Step 1:** `git mv` the project subfolder contents to `app/` preserving `src/`, `data/`, `data-for-enhancement/`, `tests/`, `requirements.txt`, `.env.example`, `.gitignore`.
- [ ] **Step 2:** Create `app/data-augmented/` and `report/`.
- [ ] **Step 3:** Verify `python -c "import ast"` and `ls app/src` shows the modules.
- [ ] **Step 4:** Commit `chore: restructure into app/`.

### Task 2: Augmented datasets

**Files:**
- Create: `app/data-augmented/item_master_canonical.csv`, `item_alias.csv`, `item_legacy_map.csv`, `corridor_sla.csv`, `scenario_presets.json`

- [ ] **Step 1:** Encode Appendix A.1 canonical master (columns: `canonical_item_id,item_id,canonical_item_name,medicine_type,temp_control,product_class`) from the playbook table.
- [ ] **Step 2:** Encode A.2 aliases (`alias_name,canonical_item_id,confidence_tier`) and A.3 legacy (`legacy_item_id,canonical_item_id,rule`).
- [ ] **Step 3:** `corridor_sla.csv`: `corridor_id,sla_tier,max_transit_hours,hospital_priority` (C1→Tier1/6, C2→Tier2/12).
- [ ] **Step 4:** `scenario_presets.json`: keys `demand_spike_20`, `corridor_closure`, `driver_shortage` with parameter blocks.
- [ ] **Step 5:** Commit `data: augmented item master + scenario presets`.

### Task 3: KPI engine (deterministic, TDD)

**Files:**
- Create: `app/src/tools/kpi_engine.py`, `app/tests/test_kpi_engine.py`

- [ ] **Step 1: Write failing test** in `test_kpi_engine.py`:

```python
import pandas as pd
from src.tools.kpi_engine import compute_kpis, ResourcePool

def test_required_trucks_and_penalty():
    units = pd.DataFrame([
        {"corridor_id": "C1_I95_NJ_BOS", "planning_day": "Day0",
         "canonical_item_id": "RMD-100", "temp_control": "Cold (2-8C)", "sla_tier": 1},
    ] * 11)
    pool = ResourcePool(driver=6, truck_standard=4, truck_temp_controlled=2)
    k = compute_kpis(units, pool, sla_map={"C1_I95_NJ_BOS": 1, "C2_NJ_PHL": 2})
    # 11 cold units -> ceil(11*1.1/10)=2 reefer trucks required
    assert k["corridors"]["C1_I95_NJ_BOS"]["Day0"]["reefer_trucks_required"] == 2
    assert k["total_penalty_score"] == 0  # 2 reefers available, no violation
```

- [ ] **Step 2:** Run `cd app && python -m pytest tests/test_kpi_engine.py -v` → expect FAIL (module missing).
- [ ] **Step 3: Implement** `kpi_engine.py`:

```python
from __future__ import annotations
from dataclasses import dataclass
from math import ceil
from typing import Dict, Any
import pandas as pd

COLD = {"Cold (2-8C)", "Strict Cold Chain (-20C)"}
TRUCK_CAP, PACK_BUFFER = 10, 1.10
PENALTY = {"tier1_sla": 100, "tier2_sla": 40, "cold_chain": 80, "delay": 10}

@dataclass
class ResourcePool:
    driver: int
    truck_standard: int
    truck_temp_controlled: int

def _trucks(n_units: int) -> int:
    return ceil(n_units * PACK_BUFFER / TRUCK_CAP) if n_units else 0

def compute_kpis(units: pd.DataFrame, pool: ResourcePool,
                 sla_map: Dict[str, int]) -> Dict[str, Any]:
    out: Dict[str, Any] = {"corridors": {}, "total_penalty_score": 0,
                           "tier1_units_impacted": 0}
    if units.empty:
        return out
    total_penalty = 0
    t1_impacted = 0
    for cid, cdf in units.groupby("corridor_id"):
        out["corridors"][cid] = {}
        for day, ddf in cdf.groupby("planning_day"):
            cold = ddf[ddf["temp_control"].isin(COLD)]
            warm = ddf[~ddf["temp_control"].isin(COLD)]
            reefer_req = _trucks(len(cold))
            std_req = _trucks(len(warm))
            out["corridors"][cid][str(day)] = {
                "units": int(len(ddf)),
                "reefer_trucks_required": reefer_req,
                "standard_trucks_required": std_req,
                "tier1_units": int((ddf["sla_tier"] == 1).sum()),
                "tier2_units": int((ddf["sla_tier"] == 2).sum()),
            }
            reefer_short = max(0, reefer_req - pool.truck_temp_controlled)
            std_short = max(0, std_req - pool.truck_standard)
            if reefer_short:
                affected = reefer_short * TRUCK_CAP
                for _, r in cold.head(affected).iterrows():
                    tier = int(r["sla_tier"])
                    total_penalty += PENALTY["tier1_sla"] if tier == 1 else PENALTY["tier2_sla"]
                    total_penalty += PENALTY["cold_chain"]
                    if tier == 1:
                        t1_impacted += 1
            if std_short:
                affected = std_short * TRUCK_CAP
                for _, r in warm.head(affected).iterrows():
                    tier = int(r["sla_tier"])
                    total_penalty += PENALTY["tier1_sla"] if tier == 1 else PENALTY["tier2_sla"]
                    if tier == 1:
                        t1_impacted += 1
    out["total_penalty_score"] = int(total_penalty)
    out["tier1_units_impacted"] = int(t1_impacted)
    return out
```

- [ ] **Step 4:** Run the test → expect PASS.
- [ ] **Step 5:** Commit `feat: deterministic KPI + penalty engine`.

### Task 4: Data reconciliation (DQ + Appendix A)

**Files:**
- Modify: `app/src/tools/csv_tools.py` (add `reconcile_shipments`)
- Create: `app/tests/test_reconciliation.py`

- [ ] **Step 1: Write failing test:**

```python
import pandas as pd
from src.tools.csv_tools import reconcile_shipments

def test_reconcile_drops_missing_uid_and_maps_legacy():
    df = pd.DataFrame([
        {"shipment_date":"2026-03-02","planning_day":"Day0","is_planning_window":1,
         "corridor_id":"C1_I95_NJ_BOS","item_id":10021,"item_name":"Remdesivir 100mg",
         "unique_item_id":"RMD-2026-0001","dispatch_location":"Boston-MGH"},
        {"shipment_date":"2026-03-02","planning_day":"Day0","is_planning_window":1,
         "corridor_id":"C1_I95_NJ_BOS","item_id":10022,"item_name":"Insulin Lispro",
         "unique_item_id":"","dispatch_location":"Boston-BWH"},
        {"shipment_date":"2026-03-02","planning_day":"Day0","is_planning_window":1,
         "corridor_id":"C2_NJ_PHL","item_id":10020,"item_name":"Remdesivir 100mg",
         "unique_item_id":"RMD-2026-1001","dispatch_location":"Philadelphia-CHOP"},
    ])
    res = reconcile_shipments(df, master_dir="data-augmented")
    valid = res["valid"]
    assert len(valid) == 2                       # missing-uid row excluded (DQ-01)
    assert (res["excluded"]["reason"] == "excluded_unresolved").sum() == 0
    assert (res["excluded"]["reason"] == "missing_unique_item_id").sum() == 1
    assert "canonical_item_id" in valid.columns
    assert valid.iloc[1]["canonical_item_id"] == "RMD-100"  # legacy 10020 -> RMD-100
```

- [ ] **Step 2:** Run `pytest tests/test_reconciliation.py -v` → FAIL.
- [ ] **Step 3: Implement** `reconcile_shipments(df, master_dir)` in `csv_tools.py`:
  - Strip cols; load `item_master_canonical.csv`, `item_alias.csv`, `item_legacy_map.csv` from `master_dir`.
  - DQ-01: drop rows with blank/NaN `unique_item_id` → excluded reason `missing_unique_item_id`.
  - Map to `canonical_item_id`: exact (`item_id`+`item_name`) → alias (`item_name`) → legacy (`item_id`); set `reason` ∈ {`exact_match`,`alias_match`,`legacy_id_map`}.
  - Unresolvable → excluded reason `excluded_unresolved`.
  - DQ-04: duplicate `unique_item_id` → keep first, flag dup count.
  - Join `temp_control` from canonical master.
  - Return `{"valid": df, "excluded": df, "stats": {...}}`.
- [ ] **Step 4:** Run test → PASS.
- [ ] **Step 5:** Commit `feat: shipment reconciliation (DQ + Appendix A)`.

### Task 5: Scenario engine (TDD)

**Files:**
- Create: `app/src/tools/scenario_engine.py`, `app/tests/test_scenario_engine.py`

- [ ] **Step 1: Write failing test:**

```python
import pandas as pd
from src.tools.scenario_engine import apply_scenario, ScenarioSpec
from src.tools.kpi_engine import ResourcePool

def _units(n, corridor="C1_I95_NJ_BOS"):
    return pd.DataFrame([{"corridor_id":corridor,"planning_day":"Day0",
        "canonical_item_id":"RMD-100","temp_control":"Cold (2-8C)","sla_tier":1}]*n)

def test_demand_spike_scales_units():
    base = _units(10)
    spec = ScenarioSpec(demand_spike_pct=20)
    units, pool = apply_scenario(base, ResourcePool(6,4,2), spec)
    assert len(units) == 12

def test_closure_removes_corridor():
    base = pd.concat([_units(5,"C1_I95_NJ_BOS"), _units(5,"C2_NJ_PHL")])
    spec = ScenarioSpec(closed_corridors=["C2_NJ_PHL"])
    units, _ = apply_scenario(base, ResourcePool(6,4,2), spec)
    assert set(units["corridor_id"]) == {"C1_I95_NJ_BOS"}

def test_shortage_reduces_pool():
    spec = ScenarioSpec(truck_temp_controlled=1)
    _, pool = apply_scenario(_units(5), ResourcePool(6,4,2), spec)
    assert pool.truck_temp_controlled == 1
```

- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3: Implement** `scenario_engine.py`:

```python
from __future__ import annotations
from dataclasses import dataclass, field
from math import floor
from typing import List, Optional
import pandas as pd
from .kpi_engine import ResourcePool

@dataclass
class ScenarioSpec:
    demand_spike_pct: float = 0.0
    closed_corridors: List[str] = field(default_factory=list)
    driver: Optional[int] = None
    truck_standard: Optional[int] = None
    truck_temp_controlled: Optional[int] = None
    weather_override: dict = field(default_factory=dict)  # {corridor_id: forced_score}

def apply_scenario(units: pd.DataFrame, pool: ResourcePool, spec: ScenarioSpec):
    df = units.copy()
    if spec.closed_corridors:
        df = df[~df["corridor_id"].isin(spec.closed_corridors)]
    if spec.demand_spike_pct:
        extra = floor(len(df) * spec.demand_spike_pct / 100.0)
        if extra > 0:
            df = pd.concat([df, df.sample(extra, replace=True, random_state=42)],
                           ignore_index=True)
    new_pool = ResourcePool(
        driver=spec.driver if spec.driver is not None else pool.driver,
        truck_standard=spec.truck_standard if spec.truck_standard is not None else pool.truck_standard,
        truck_temp_controlled=spec.truck_temp_controlled if spec.truck_temp_controlled is not None else pool.truck_temp_controlled,
    )
    return df.reset_index(drop=True), new_pool
```

- [ ] **Step 4:** Run → PASS.
- [ ] **Step 5:** Commit `feat: scenario disruption engine`.

### Task 6: State schema + new prompts/agents

**Files:**
- Create: `app/src/state.py`
- Modify: `app/src/prompts.py`, `app/src/agents.py`

- [ ] **Step 1:** `state.py`: `AppState` TypedDict (total=False) with fields from spec §3.3.
- [ ] **Step 2:** Add to `prompts.py`: `IMPACT_PROMPT`, `CONTINGENCY_PROMPT`, `AUDIT_PROMPT` (system+user templates; audit must output a line `COMPLIANT: yes|no` + reasons; planner must reference playbook §13 allocation policy).
- [ ] **Step 3:** Add to `agents.py`: `run_impact_agent(baseline_kpis, scenario_kpis, scenario_spec)`, `run_contingency_agent(business_context, impact, scenario_kpis)`, `run_audit_agent(business_context, contingency_plan, scenario_kpis)` returning `(text, compliant: bool)` by parsing the `COMPLIANT:` line.
- [ ] **Step 4:** `cd app && python -c "from src.agents import run_audit_agent"` → no import error.
- [ ] **Step 5:** Commit `feat: state schema + impact/contingency/audit agents`.

### Task 7: Rewire LangGraph with cyclic audit loop

**Files:**
- Modify: `app/src/graph.py`

- [ ] **Step 1:** Import new tools/agents; build nodes per spec §3.2 (`data_reconciliation`, `baseline_kpis`, `scenario_parser`, `disruption_engine`, `impact_analysis`, `contingency_planner`, `audit`, `report`).
- [ ] **Step 2:** `node_audit` sets `audit_iterations = state.get("audit_iterations",0)+1` and `audit_result`.
- [ ] **Step 3:** Conditional edge function `route_after_audit`: return `"contingency_planner"` if `not compliant and audit_iterations < 2` else `"report"`. Wire `g.add_conditional_edges("audit", route_after_audit, {...})`.
- [ ] **Step 4:** Each node appends a `cowork_trace` event `{"node","summary","ts"}` (key state passed downstream).
- [ ] **Step 5:** Keep `email` node optional after `report`.
- [ ] **Step 6:** `python -c "from src.graph import build_graph; build_graph()"` → compiles.
- [ ] **Step 7:** Commit `feat: cyclic what-if LangGraph flow`.

### Task 8: CLI entrypoint

**Files:**
- Modify: `app/src/main.py`

- [ ] **Step 1:** Argparse: `--scenario <json>`, `--preset <key>`, `--no-llm` (smoke). Load preset → `ScenarioSpec`. Invoke graph. Print KPI comparison + penalty + first 2000 chars of report.
- [ ] **Step 2:** `cd app && python -m src.main --preset demand_spike_20` runs end-to-end (needs `OPENAI_API_KEY`; otherwise document `--no-llm`).
- [ ] **Step 3:** Commit `feat: CLI scenario runner`.

### Task 9: Cowork trace + Streamlit UI

**Files:**
- Create: `app/src/viz/cowork_trace.py`, `app/src/streamlit_app.py`

- [ ] **Step 1:** `cowork_trace.py`: helper `stream_graph(app, state)` yielding `(node_name, partial_state)` via `app.stream(state, stream_mode="updates")`.
- [ ] **Step 2:** `streamlit_app.py`: sidebar scenario builder (demand slider, closure dropdown, driver/std/reefer number inputs, weather override, Run button).
- [ ] **Step 3:** On Run: build `ScenarioSpec`, iterate `stream_graph`, update an Agent Cowork expander live (node ✓ + one-line hand-off summary; show audit iteration count).
- [ ] **Step 4:** Render baseline-vs-scenario KPI metrics (`st.metric` deltas), per-corridor `matplotlib` bar chart, penalty breakdown, contingency text, `st.html(report_html)`.
- [ ] **Step 5:** `streamlit run src/streamlit_app.py` launches without import error (manual visual check noted in report).
- [ ] **Step 6:** Commit `feat: minimalist Streamlit UI + agent cowork trace`.

### Task 10: Smoke test (LLM monkeypatched)

**Files:**
- Modify: `app/tests/test_smoke.py`

- [ ] **Step 1:** Monkeypatch `agents.run_*` to return canned strings (audit returns COMPLIANT yes on 2nd call to exercise loop). Build graph, invoke with a tiny fixture CSV, assert `report_html` non-empty and `audit_iterations >= 1`.
- [ ] **Step 2:** `cd app && python -m pytest tests/ -v` → all PASS.
- [ ] **Step 3:** Commit `test: end-to-end smoke with mocked LLM`.

### Task 11: requirements, .env.example, READMEs

**Files:**
- Modify: `app/requirements.txt`, `app/.env.example`
- Create: `README.md` (root), `app/README.md`

- [ ] **Step 1:** Add `streamlit>=1.36`, `matplotlib>=3.8`, `tabulate>=0.9` to requirements.
- [ ] **Step 2:** `.env.example`: `OPENAI_API_KEY=`, optional weather/email vars, `REPORT_EMAIL_TO=` (blank disables email). No secrets.
- [ ] **Step 3:** Root `README.md`: project overview, structure map, setup, **command-line example**, Streamlit launch command, link to report. Easy-to-follow tone, a diagram of the graph.
- [ ] **Step 4:** `app/README.md`: app-specific run notes.
- [ ] **Step 5:** Commit `docs: deployment guide + env/requirements`.

### Task 12: Technical & Business Report

**Files:**
- Create: `report/Technical_Business_Report.md`

- [ ] **Step 1:** Write all PDF-required sections: Executive summary (stakeholder + pain point), Key assumptions (spec §10), Technical methodology (architecture enhancements: new nodes/conditional cyclic edge; agent design: new prompts/tools), Results & validation (sample baseline-vs-scenario output + how tests validate the engine), Limitations & next steps. Easy-to-follow tone, includes the graph diagram and a sample penalty-breakdown table.
- [ ] **Step 2:** Commit `docs: technical & business report`.

### Task 13: Final verification

- [ ] **Step 1:** `cd app && python -m pytest tests/ -v` → all green.
- [ ] **Step 2:** `python -c "from src.graph import build_graph; build_graph()"` → compiles.
- [ ] **Step 3:** Run CLI `--no-llm` smoke path end-to-end; confirm KPI deltas + penalty print.
- [ ] **Step 4:** Grep repo for committed secrets (`OPENAI_API_KEY=sk-`), ensure none.
- [ ] **Step 5:** Final commit if anything pending; report completion.
