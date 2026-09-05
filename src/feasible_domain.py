"""Build sparse feasible Region-StartHour options for scheduling tasks."""

from __future__ import annotations

from math import floor

import pandas as pd

from .config import (
    REGIONS,
    SCHEDULE_ARRIVAL_END,
    SCHEDULE_ARRIVAL_START,
    TERMINAL_TIME,
)


FeasibleDomains = dict[int, list[tuple[str, int]]]


def select_schedule_tasks(tasks: pd.DataFrame) -> pd.DataFrame:
    """Select actual arrivals in hours 2376-2399 and add time fields."""

    selected = tasks.loc[
        tasks["ArrivalHour"].between(
            SCHEDULE_ARRIVAL_START, SCHEDULE_ARRIVAL_END
        )
    ].copy()
    selected["DurationHour"] = selected["EstimatedDuration_min"] / 60
    selected["MaxDelayHour"] = (
        selected["LatestFinishHour"]
        - selected["ArrivalHour"]
        - selected["DurationHour"]
    )
    return selected.reset_index(drop=True)


def build_feasible_domains(
    tasks: pd.DataFrame,
    latency: pd.DataFrame,
) -> FeasibleDomains:
    """Return feasible (TargetRegion, StartHour) options for each task."""

    latency_map = latency.set_index(["FromRegion", "ToRegion"])[
        "NetworkLatency_ms"
    ].to_dict()
    domains: FeasibleDomains = {}
    infeasible: list[str] = []

    for task in tasks.itertuples(index=False):
        task_id = int(task.TaskID)
        target_regions = [
            region
            for region in REGIONS
            if latency_map[(task.SourceRegion, region)] <= task.MaxLatency_ms
        ]

        duration = task.EstimatedDuration_min / 60
        finish_limit = min(task.LatestFinishHour, TERMINAL_TIME)
        earliest_start = max(task.ArrivalHour, task.EarliestStartHour)

        if task.TaskType == "RealTimeInference":
            starts = [int(task.ArrivalHour)]
            if (
                task.ArrivalHour < earliest_start
                or task.ArrivalHour + duration > finish_limit + 1e-9
            ):
                starts = []
        else:
            latest_start = floor(finish_limit - duration + 1e-9)
            starts = list(range(int(earliest_start), latest_start + 1))

        options = [(region, start) for region in target_regions for start in starts]
        domains[task_id] = options

        if not options:
            reasons = []
            if not target_regions:
                reasons.append("no region satisfies MaxLatency_ms")
            if not starts:
                reasons.append("no integer StartHour satisfies the time window")
            infeasible.append(f"TaskID={task_id}: {', '.join(reasons)}")

    if infeasible:
        raise ValueError("Empty feasible domains:\n" + "\n".join(infeasible))
    return domains

