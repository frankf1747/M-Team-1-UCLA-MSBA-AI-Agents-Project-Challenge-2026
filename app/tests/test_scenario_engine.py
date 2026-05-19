import pandas as pd
from src.tools.scenario_engine import apply_scenario, ScenarioSpec
from src.tools.kpi_engine import ResourcePool


def _units(n, corridor="C1_I95_NJ_BOS"):
    return pd.DataFrame([{
        "corridor_id": corridor, "planning_day": "Day0",
        "canonical_item_id": "RMD-100", "temp_control": "Cold (2-8C)",
        "sla_tier": 1,
    }] * n)


def test_demand_spike_scales_units():
    units, _ = apply_scenario(_units(10), ResourcePool(6, 4, 2),
                              ScenarioSpec(demand_spike_pct=20))
    assert len(units) == 12


def test_closure_removes_corridor():
    base = pd.concat([_units(5, "C1_I95_NJ_BOS"), _units(5, "C2_NJ_PHL")])
    units, _ = apply_scenario(base, ResourcePool(6, 4, 2),
                              ScenarioSpec(closed_corridors=["C2_NJ_PHL"]))
    assert set(units["corridor_id"]) == {"C1_I95_NJ_BOS"}


def test_shortage_reduces_pool_only_where_specified():
    _, pool = apply_scenario(_units(5), ResourcePool(6, 4, 2),
                             ScenarioSpec(truck_temp_controlled=1))
    assert pool.truck_temp_controlled == 1
    assert pool.driver == 6 and pool.truck_standard == 4
