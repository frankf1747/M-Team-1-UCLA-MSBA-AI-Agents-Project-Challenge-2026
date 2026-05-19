"""Deterministic KPI + penalty engine, grounded in the SeeWeeS playbook (sections 8 and 13)."""
from __future__ import annotations
from dataclasses import dataclass
from math import ceil
from typing import Dict, Any
import pandas as pd

COLD_FLAGS = {"Cold (2-8C)", "Strict Cold Chain (-20C)"}
TRUCK_CAPACITY = 10          # playbook 8.1: standard truck capacity, volume units
PACK_BUFFER = 1.10           # playbook 8.1: +10% packing inefficiency buffer

# playbook 13.2 penalty model (points per affected unit)
PENALTY_TIER1_SLA = 100
PENALTY_TIER2_SLA = 40
PENALTY_COLD_CHAIN = 80      # additive, on top of any SLA penalty
PENALTY_DELAY = 10           # within SLA but not dispatched on requested day


@dataclass
class ResourcePool:
    driver: int
    truck_standard: int
    truck_temp_controlled: int


def _trucks_required(n_units: int) -> int:
    if n_units <= 0:
        return 0
    return ceil(n_units * PACK_BUFFER / TRUCK_CAPACITY)


def compute_kpis(units: pd.DataFrame, pool: ResourcePool) -> Dict[str, Any]:
    """Compute corridor/day KPIs and the total penalty score.

    `units` must contain: corridor_id, planning_day, temp_control, sla_tier.
    Resource pools are shared per day across corridors (playbook 13.1).
    """
    out: Dict[str, Any] = {
        "corridors": {},
        "total_penalty_score": 0,
        "tier1_units_impacted": 0,
        "total_units": int(len(units)),
        "totals": {},
    }
    if units.empty:
        return out

    total_penalty = 0
    t1_impacted = 0
    tot_reefer_req = tot_std_req = 0

    if "disrupted" not in units.columns:
        units = units.assign(disrupted=False)

    # Stranded units (e.g. closed corridor): undeliverable -> full SLA penalty.
    stranded = units[units["disrupted"] == True]  # noqa: E712
    for _, r in stranded.iterrows():
        tier = int(r["sla_tier"])
        total_penalty += PENALTY_TIER1_SLA if tier == 1 else PENALTY_TIER2_SLA
        if str(r["temp_control"]) in COLD_FLAGS:
            total_penalty += PENALTY_COLD_CHAIN
        if tier == 1:
            t1_impacted += 1
    out["stranded_units"] = int(len(stranded))

    units = units[units["disrupted"] != True]  # noqa: E712
    if units.empty:
        out["total_penalty_score"] = int(total_penalty)
        out["tier1_units_impacted"] = int(t1_impacted)
        return out

    # Resource pools are shared per day across corridors (playbook 13.1).
    for day, daydf in units.groupby("planning_day"):
        reefer_avail = pool.truck_temp_controlled
        std_avail = pool.truck_standard
        driver_avail = pool.driver
        penalized_idx: set = set()

        for cid, ddf in daydf.groupby("corridor_id"):
            out["corridors"].setdefault(str(cid), {})
            cold = ddf[ddf["temp_control"].isin(COLD_FLAGS)]
            warm = ddf[~ddf["temp_control"].isin(COLD_FLAGS)]
            wx = float(ddf["wx_buffer"].max()) if "wx_buffer" in ddf.columns else 1.0
            reefer_req = _trucks_required(ceil(len(cold) * wx))
            std_req = _trucks_required(ceil(len(warm) * wx))
            tot_reefer_req += reefer_req
            tot_std_req += std_req

            out["corridors"][str(cid)][str(day)] = {
                "units": int(len(ddf)),
                "reefer_trucks_required": reefer_req,
                "standard_trucks_required": std_req,
                "tier1_units": int((ddf["sla_tier"] == 1).sum()),
                "tier2_units": int((ddf["sla_tier"] == 2).sum()),
            }

            # Truck shortfalls (reefer/standard), drawing from the shared day pool.
            reefer_short = max(0, reefer_req - reefer_avail)
            std_short = max(0, std_req - std_avail)
            reefer_avail = max(0, reefer_avail - reefer_req)
            std_avail = max(0, std_avail - std_req)

            for _, r in cold.head(reefer_short * TRUCK_CAPACITY).iterrows():
                tier = int(r["sla_tier"])
                total_penalty += PENALTY_TIER1_SLA if tier == 1 else PENALTY_TIER2_SLA
                total_penalty += PENALTY_COLD_CHAIN
                penalized_idx.add(r.name)
                if tier == 1:
                    t1_impacted += 1
            for _, r in warm.head(std_short * TRUCK_CAPACITY).iterrows():
                tier = int(r["sla_tier"])
                total_penalty += PENALTY_TIER1_SLA if tier == 1 else PENALTY_TIER2_SLA
                penalized_idx.add(r.name)
                if tier == 1:
                    t1_impacted += 1

        # Driver shortfall: each truck needs a driver (playbook 13.1).
        day_trucks = sum(
            out["corridors"][str(c)][str(day)]["reefer_trucks_required"]
            + out["corridors"][str(c)][str(day)]["standard_trucks_required"]
            for c in daydf["corridor_id"].unique()
        )
        driver_short_trucks = max(0, day_trucks - driver_avail)
        if driver_short_trucks:
            remaining = daydf[~daydf.index.isin(penalized_idx)]
            for _, r in remaining.head(driver_short_trucks * TRUCK_CAPACITY).iterrows():
                tier = int(r["sla_tier"])
                total_penalty += PENALTY_TIER1_SLA if tier == 1 else PENALTY_TIER2_SLA
                if str(r["temp_control"]) in COLD_FLAGS:
                    total_penalty += PENALTY_COLD_CHAIN
                if tier == 1:
                    t1_impacted += 1

    out["total_penalty_score"] = int(total_penalty)
    out["tier1_units_impacted"] = int(t1_impacted)
    out["totals"] = {
        "reefer_trucks_required": int(tot_reefer_req),
        "standard_trucks_required": int(tot_std_req),
        "reefer_trucks_available": pool.truck_temp_controlled,
        "standard_trucks_available": pool.truck_standard,
        "drivers_available": pool.driver,
        "drivers_required": int(tot_reefer_req + tot_std_req),
        "tier1_units": int((units["sla_tier"] == 1).sum()),
        "tier2_units": int((units["sla_tier"] == 2).sum()),
    }
    return out
