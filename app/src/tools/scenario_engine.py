"""Disruption engine: applies a what-if ScenarioSpec to the reconciled shipment
feed and the resource pool. Pure/deterministic so impact numbers are defensible."""
from __future__ import annotations
from dataclasses import dataclass, field
from math import floor
from typing import List, Optional, Dict, Tuple
import pandas as pd

from .kpi_engine import ResourcePool


@dataclass
class ScenarioSpec:
    demand_spike_pct: float = 0.0
    closed_corridors: List[str] = field(default_factory=list)
    driver: Optional[int] = None
    truck_standard: Optional[int] = None
    truck_temp_controlled: Optional[int] = None
    weather_override: Dict[str, int] = field(default_factory=dict)  # corridor_id -> 0..3
    label: str = "Custom scenario"

    @classmethod
    def from_preset(cls, preset: dict) -> "ScenarioSpec":
        return cls(
            demand_spike_pct=preset.get("demand_spike_pct", 0) or 0,
            closed_corridors=list(preset.get("closed_corridors") or []),
            driver=preset.get("driver"),
            truck_standard=preset.get("truck_standard"),
            truck_temp_controlled=preset.get("truck_temp_controlled"),
            weather_override=dict(preset.get("weather_override") or {}),
            label=preset.get("label", "Custom scenario"),
        )

    def is_baseline(self) -> bool:
        return (not self.demand_spike_pct and not self.closed_corridors
                and self.driver is None and self.truck_standard is None
                and self.truck_temp_controlled is None and not self.weather_override)


def apply_scenario(units: pd.DataFrame, pool: ResourcePool,
                   spec: ScenarioSpec) -> Tuple[pd.DataFrame, ResourcePool]:
    df = units.copy()

    if spec.closed_corridors:
        df = df[~df["corridor_id"].isin(spec.closed_corridors)]

    if spec.demand_spike_pct and len(df):
        extra = floor(len(df) * spec.demand_spike_pct / 100.0)
        if extra > 0:
            df = pd.concat(
                [df, df.sample(extra, replace=True, random_state=42)],
                ignore_index=True,
            )

    new_pool = ResourcePool(
        driver=spec.driver if spec.driver is not None else pool.driver,
        truck_standard=(spec.truck_standard if spec.truck_standard is not None
                        else pool.truck_standard),
        truck_temp_controlled=(spec.truck_temp_controlled
                               if spec.truck_temp_controlled is not None
                               else pool.truck_temp_controlled),
    )
    return df.reset_index(drop=True), new_pool
