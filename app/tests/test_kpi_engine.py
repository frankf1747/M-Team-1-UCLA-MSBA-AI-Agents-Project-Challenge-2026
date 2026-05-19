import pandas as pd
from src.tools.kpi_engine import compute_kpis, ResourcePool


def _cold_units(n, corridor="C1_I95_NJ_BOS", tier=1):
    return pd.DataFrame([{
        "corridor_id": corridor, "planning_day": "Day0",
        "canonical_item_id": "RMD-100", "temp_control": "Cold (2-8C)",
        "sla_tier": tier,
    }] * n)


def test_required_trucks_no_violation():
    units = _cold_units(11)
    pool = ResourcePool(driver=6, truck_standard=4, truck_temp_controlled=2)
    k = compute_kpis(units, pool)
    cell = k["corridors"]["C1_I95_NJ_BOS"]["Day0"]
    assert cell["reefer_trucks_required"] == 2  # ceil(11*1.1/10)=2
    assert k["total_penalty_score"] == 0  # 2 reefers available


def test_driver_shortage_strands_units():
    # 11 cold units -> 2 reefer trucks needed -> 2 drivers needed.
    units = _cold_units(11)
    pool = ResourcePool(driver=1, truck_standard=4, truck_temp_controlled=2)
    k = compute_kpis(units, pool)
    # reefer trucks available (no truck penalty) but only 1 driver for 2 trucks
    # -> 1 truck undriven -> up to 10 units stranded (Tier1 100 + cold 80).
    assert k["total_penalty_score"] == 10 * 180
    assert k["tier1_units_impacted"] == 10


def test_reefer_shortage_creates_tier1_cold_penalty():
    units = _cold_units(11)
    pool = ResourcePool(driver=6, truck_standard=4, truck_temp_controlled=1)
    k = compute_kpis(units, pool)
    # 1 reefer short -> 10 units impacted -> each Tier1(100)+cold(80)=180
    assert k["total_penalty_score"] == 10 * 180
    assert k["tier1_units_impacted"] == 10
