"""Sparse hourly overlap coefficients for non-preemptive tasks."""

from __future__ import annotations

from collections import defaultdict
from math import ceil

import pandas as pd

from .config import RESOURCE_HOURS
from .feasible_domain import FeasibleDomains


OverlapValues = dict[tuple[int, int, int], float]
ActiveOptions = dict[tuple[str, int], list[tuple[int, str, int]]]


def hourly_overlap(start_hour: int, duration_hour: float, hour: int) -> float:
    """Return overlap with the interval [hour, hour + 1)."""

    value = max(
        0.0,
        min(start_hour + duration_hour, hour + 1) - max(start_hour, hour),
    )
    return round(value, 12)


def precompute_overlaps(
    tasks: pd.DataFrame,
    feasible_domains: FeasibleDomains,
) -> tuple[OverlapValues, ActiveOptions]:
    """Build nonzero overlap values and a Region-Hour reverse index."""

    duration_by_task = tasks.set_index("TaskID")["DurationHour"].to_dict()
    resource_hours = set(RESOURCE_HOURS)
    overlaps: OverlapValues = {}
    active_options: defaultdict[
        tuple[str, int], list[tuple[int, str, int]]
    ] = defaultdict(list)

    for task_id, options in feasible_domains.items():
        duration = float(duration_by_task[task_id])
        hours_by_start: dict[int, list[int]] = {}

        for start in {start for _, start in options}:
            active_hours = []
            for hour in range(start, ceil(start + duration)):
                if hour not in resource_hours:
                    continue
                value = hourly_overlap(start, duration, hour)
                if value > 0:
                    overlaps[(task_id, start, hour)] = value
                    active_hours.append(hour)
            hours_by_start[start] = active_hours

        for region, start in options:
            for hour in hours_by_start[start]:
                active_options[(region, hour)].append((task_id, region, start))

    return overlaps, dict(active_options)

