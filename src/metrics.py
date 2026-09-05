"""Evaluation metrics used by Question 1."""

from __future__ import annotations

import pandas as pd

from .config import REGIONS, TASK_TYPES
from .demand_builder import aggregate_region_demand, aggregate_system_demand


STAT_COLUMNS = ["count", "mean", "std", "min", "median", "max", "sum", "zero_ratio"]


def _describe(values: pd.Series) -> dict[str, float | int]:
    return {
        "count": int(values.size),
        "mean": float(values.mean()),
        "std": float(values.std(ddof=0)),
        "min": float(values.min()),
        "median": float(values.median()),
        "max": float(values.max()),
        "sum": float(values.sum()),
        "zero_ratio": float(values.eq(0).mean()),
    }


def build_demand_statistics(demand: pd.DataFrame) -> pd.DataFrame:
    """Describe the complete hourly demand series at four aggregation levels."""

    required = {"Hour", "Region", "TaskType", "GPU_Demand"}
    missing = required - set(demand.columns)
    if missing:
        raise ValueError(f"Missing demand columns: {sorted(missing)}")

    region_hour = aggregate_region_demand(demand)
    task_type_hour = (
        demand.groupby(["Hour", "TaskType"], as_index=False, sort=True)["GPU_Demand"]
        .sum()
    )
    system_hour = aggregate_system_demand(demand)

    rows = [
        {
            "Level": "system",
            "Region": None,
            "TaskType": None,
            **_describe(system_hour["GPU_Demand"]),
        }
    ]

    for region in REGIONS:
        values = region_hour.loc[region_hour["Region"].eq(region), "GPU_Demand"]
        rows.append(
            {"Level": "region", "Region": region, "TaskType": None, **_describe(values)}
        )

    for task_type in TASK_TYPES:
        values = task_type_hour.loc[
            task_type_hour["TaskType"].eq(task_type), "GPU_Demand"
        ]
        rows.append(
            {
                "Level": "task_type",
                "Region": None,
                "TaskType": task_type,
                **_describe(values),
            }
        )

    for region in REGIONS:
        for task_type in TASK_TYPES:
            values = demand.loc[
                demand["Region"].eq(region) & demand["TaskType"].eq(task_type),
                "GPU_Demand",
            ]
            rows.append(
                {
                    "Level": "region_task_type",
                    "Region": region,
                    "TaskType": task_type,
                    **_describe(values),
                }
            )

    columns = ["Level", "Region", "TaskType", *STAT_COLUMNS]
    return pd.DataFrame(rows, columns=columns)

