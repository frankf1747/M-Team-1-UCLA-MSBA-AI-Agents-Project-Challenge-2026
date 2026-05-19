# app/ — SeeWeeS What-if Simulation

See the repository root `README.md` for the full deployment guide and
architecture diagram. Quick reference:

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env

# offline deterministic run (no API key)
python -m src.main --preset corridor_closure --no-llm

# web UI (open http://localhost:8000)
uvicorn web.server:app --app-dir src --port 8000

# tests
python -m pytest tests/ -q
```

**Data**
- `data/` — original provided PDF + CSV (unchanged).
- `data-for-enhancement/` — provided playbook, multi-corridor feed, resource file.
- `data-augmented/` — our augmented datasets:
  - `item_master_canonical.csv`, `item_alias.csv`, `item_legacy_map.csv` —
    Appendix A encoded for reconciliation.
  - `corridor_sla.csv` — corridor → SLA tier / hospital priority assumptions.
  - `scenario_presets.json` — the disruption presets.
  - `incoming_shipments_scenario.csv` — realistic 48h planning feed
    (regenerate with `python data-augmented/make_scenario_dataset.py`).

The original workshop feed `Incoming_shipments_14d_multi_corridor.csv` has very
few planning-window rows, so a +20% spike never stresses the fleet. The PDF
explicitly invites simulating realistic values; `incoming_shipments_scenario.csv`
is sized so baseline is feasible (penalty 0) and each disruption clearly moves
KPIs. Point `--csv` at the 14-day file if you want trend/history data instead.
