"""Build hourly GPU demand series from task arrivals."""

from __future__ import annotations

import pandas as pd

from .config import DEMAND_HOURS, REGIONS, TASK_TYPES


DEMAND_COLUMNS = {"ArrivalHour", "SourceRegion", "TaskType", "GPU_Demand"}


def build_demand_series(tasks: pd.DataFrame) -> pd.DataFrame:
    """Return the complete Hour-Region-TaskType GPU arrival demand table."""

    missing = DEMAND_COLUMNS - set(tasks.columns)
    if missing:
        raise ValueError(f"Missing task columns: {sorted(missing)}")

    full_index = pd.MultiIndex.from_product(
        [DEMAND_HOURS, REGIONS, TASK_TYPES],
        names=["Hour", "Region", "TaskType"],
    )
    observed = (
        tasks.groupby(
            ["ArrivalHour", "SourceRegion", "TaskType"],
            observed=True,
        )["GPU_Demand"]
        .sum()
        .rename_axis(["Hour", "Region", "TaskType"])
    )

    return (
        observed.reindex(full_index, fill_value=0)
        .rename("GPU_Demand")
        .reset_index()
    )


def aggregate_region_demand(demand: pd.DataFrame) -> pd.DataFrame:
    """Sum the three task types for every Region-Hour pair."""

    return (
        demand.groupby(["Hour", "Region"], as_index=False, sort=True)["GPU_Demand"]
        .sum()
    )


def aggregate_system_demand(demand: pd.DataFrame) -> pd.DataFrame:
    """Sum all regions and task types for every hour."""

    return demand.groupby("Hour", as_index=False, sort=True)["GPU_Demand"].sum()

