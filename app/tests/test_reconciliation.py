import os
import pandas as pd
from src.tools.csv_tools import reconcile_shipments

MASTER = os.path.join(os.path.dirname(__file__), "..", "data-augmented")


def _row(**kw):
    base = {"shipment_date": "2026-03-02", "planning_day": "Day0",
            "is_planning_window": 1, "corridor_id": "C1_I95_NJ_BOS",
            "item_id": 10021, "item_name": "Remdesivir 100mg",
            "unique_item_id": "RMD-2026-0001", "dispatch_location": "Boston-MGH"}
    base.update(kw)
    return base


def test_drops_missing_uid_and_maps_legacy():
    df = pd.DataFrame([
        _row(),
        _row(item_id=10022, item_name="Insulin Lispro", unique_item_id=""),  # DQ-01
        _row(item_id=10020, unique_item_id="RMD-2026-1001"),                  # legacy 10020
    ])
    res = reconcile_shipments(df, master_dir=MASTER)
    valid = res["valid"]
    assert len(valid) == 2
    assert (res["excluded"]["reason"] == "missing_unique_item_id").sum() == 1
    assert "canonical_item_id" in valid.columns
    legacy_row = valid[valid["item_id"] == 10020].iloc[0]
    assert legacy_row["canonical_item_id"] == "RMD-100"
    assert legacy_row["reason"] == "legacy_id_map"


def test_alias_match_and_temp_control_joined():
    df = pd.DataFrame([_row(item_id=10070, item_name="Albuterol Inhaler 90mcg",
                            unique_item_id="ALB-1")])
    res = reconcile_shipments(df, master_dir=MASTER)
    row = res["valid"].iloc[0]
    assert row["canonical_item_id"] == "ALB-INH"
    assert row["reason"] == "alias_match"
    assert row["temp_control"] == "Room Temp (20-25C)"
