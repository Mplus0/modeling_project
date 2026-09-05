"""Independent validation of a decoded scheduling result."""

from __future__ import annotations

from dataclasses import dataclass
from math import ceil

import pandas as pd

from .config import REGIONS, RESOURCE_HOURS, TERMINAL_TIME
from .overlap import hourly_overlap


@dataclass(slots=True)
class ScheduleValidationResult:
    summary: dict[str, int | float]
    violations: pd.DataFrame
    resources: pd.DataFrame

    @property
    def is_valid(self) -> bool:
        return self.violations.empty


def validate_schedule(
    schedule: pd.DataFrame,
    tasks: pd.DataFrame,
    gpu_info: pd.DataFrame,
    latency: pd.DataFrame,
    power_map: pd.DataFrame,
    region_time: pd.DataFrame,
    tolerance: float = 1e-6,
) -> ScheduleValidationResult:
    """Recalculate every hard constraint from the decoded schedule."""

    required = {"TaskID", "TargetRegion", "StartHour"}
    missing_columns = required - set(schedule.columns)
    if missing_columns:
        raise ValueError(f"Missing schedule columns: {sorted(missing_columns)}")

    violations: list[dict] = []
    expected_ids = set(tasks["TaskID"])
    schedule_counts = schedule["TaskID"].value_counts()
    scheduled_ids = set(schedule_counts.index)

    for task_id in sorted(expected_ids - scheduled_ids):
        violations.append(
            {"Category": "missing_task", "TaskID": task_id, "Detail": "not scheduled"}
        )
    for task_id in sorted(scheduled_ids - expected_ids):
        violations.append(
            {"Category": "unknown_task", "TaskID": task_id, "Detail": "not in input"}
        )
    for task_id, count in schedule_counts[schedule_counts.ne(1)].items():
        violations.append(
            {
                "Category": "duplicate_task",
                "TaskID": task_id,
                "Detail": f"scheduled {count} times",
            }
        )

    task_columns = [
        "TaskID",
        "TaskType",
        "ArrivalHour",
        "SourceRegion",
        "GPU_Demand",
        "EstimatedDuration_min",
        "EarliestStartHour",
        "LatestFinishHour",
        "MaxLatency_ms",
    ]
    assigned = schedule[list(required)].merge(
        tasks[task_columns], on="TaskID", how="inner", validate="many_to_one"
    )
    assigned["DurationHour"] = assigned["EstimatedDuration_min"] / 60
    assigned["FinishHour"] = assigned["StartHour"] + assigned["DurationHour"]

    latency_map = latency.set_index(["FromRegion", "ToRegion"])[
        "NetworkLatency_ms"
    ].to_dict()
    unit_power = power_map.set_index("TaskType")[
        "GPU_Power_MW_per_EquivalentGPU"
    ].to_dict()

    deadline_ok_ids: set[int] = set()
    sla_violations = 0
    deadline_violations = 0
    terminal_violations = 0

    for row in assigned.itertuples(index=False):
        task_id = int(row.TaskID)
        if row.StartHour != int(row.StartHour):
            violations.append(
                {"Category": "noninteger_start", "TaskID": task_id, "Detail": row.StartHour}
            )
        if row.StartHour < max(row.ArrivalHour, row.EarliestStartHour) - tolerance:
            violations.append(
                {"Category": "early_start", "TaskID": task_id, "Detail": row.StartHour}
            )
        if row.TaskType == "RealTimeInference" and row.StartHour != row.ArrivalHour:
            violations.append(
                {
                    "Category": "realtime_delay",
                    "TaskID": task_id,
                    "Detail": f"start={row.StartHour}, arrival={row.ArrivalHour}",
                }
            )

        actual_latency = latency_map.get((row.SourceRegion, row.TargetRegion))
        if actual_latency is None or actual_latency > row.MaxLatency_ms + tolerance:
            sla_violations += 1
            violations.append(
                {
                    "Category": "sla",
                    "TaskID": task_id,
                    "Detail": f"latency={actual_latency}, limit={row.MaxLatency_ms}",
                }
            )

        deadline_ok = row.FinishHour <= row.LatestFinishHour + tolerance
        terminal_ok = row.FinishHour <= TERMINAL_TIME + tolerance
        if not deadline_ok:
            deadline_violations += 1
            violations.append(
                {
                    "Category": "deadline",
                    "TaskID": task_id,
                    "Detail": f"finish={row.FinishHour}, limit={row.LatestFinishHour}",
                }
            )
        if not terminal_ok:
            terminal_violations += 1
            violations.append(
                {
                    "Category": "terminal",
                    "TaskID": task_id,
                    "Detail": f"finish={row.FinishHour}, limit={TERMINAL_TIME}",
                }
            )
        if deadline_ok and terminal_ok and schedule_counts.get(task_id, 0) == 1:
            deadline_ok_ids.add(task_id)

    resource_index = pd.MultiIndex.from_product(
        [RESOURCE_HOURS, REGIONS], names=["Hour", "Region"]
    )
    resources = resource_index.to_frame(index=False)
    resources["GPU_Used"] = 0.0
    resources["AI_IT_Power_MW"] = 0.0
    resources = resources.set_index(["Region", "Hour"])
    resource_hours = set(RESOURCE_HOURS)

    for row in assigned.itertuples(index=False):
        if row.TargetRegion not in REGIONS or row.StartHour != int(row.StartHour):
            continue
        start = int(row.StartHour)
        for hour in range(start, ceil(row.FinishHour)):
            if hour not in resource_hours:
                continue
            overlap = hourly_overlap(start, row.DurationHour, hour)
            gpu = row.GPU_Demand * overlap
            resources.loc[(row.TargetRegion, hour), "GPU_Used"] += gpu
            resources.loc[(row.TargetRegion, hour), "AI_IT_Power_MW"] += (
                gpu * unit_power[row.TaskType]
            )

    gpu_parameters = gpu_info.set_index("Region")
    non_ai_load = region_time.set_index(["Region", "Hour"])[
        "NonAI_IT_Load_MW"
    ]
    resources["Available_GPU"] = [
        gpu_parameters.loc[region, "Available_GPU"] for region, _ in resources.index
    ]
    resources["GPU_Utilization"] = resources["GPU_Used"] / resources["Available_GPU"]
    resources["NonAI_IT_Load_MW"] = [
        non_ai_load.loc[(region, hour)] for region, hour in resources.index
    ]
    resources["Total_IT_Power_MW"] = (
        resources["NonAI_IT_Load_MW"] + resources["AI_IT_Power_MW"]
    )
    resources["Max_IT_Power_MW"] = [
        gpu_parameters.loc[region, "Max_IT_Power_MW"] for region, _ in resources.index
    ]
    resources["PUE"] = [gpu_parameters.loc[region, "PUE"] for region, _ in resources.index]
    resources["Facility_Power_MW"] = resources["PUE"] * resources["Total_IT_Power_MW"]
    resources["Max_Facility_Power_MW"] = [
        gpu_parameters.loc[region, "Max_Facility_Power_MW"]
        for region, _ in resources.index
    ]
    resources = resources.reset_index().sort_values(["Hour", "Region"])

    gpu_overload = resources["GPU_Used"] > resources["Available_GPU"] + tolerance
    it_overload = resources["Total_IT_Power_MW"] > resources["Max_IT_Power_MW"] + tolerance
    facility_overload = (
        resources["Facility_Power_MW"]
        > resources["Max_Facility_Power_MW"] + tolerance
    )

    for category, mask in (
        ("gpu_overload", gpu_overload),
        ("it_power_overload", it_overload),
        ("facility_power_overload", facility_overload),
    ):
        for row in resources.loc[mask].itertuples(index=False):
            violations.append(
                {
                    "Category": category,
                    "Region": row.Region,
                    "Hour": row.Hour,
                    "Detail": category,
                }
            )

    scheduled_once = expected_ids & set(schedule_counts[schedule_counts.eq(1)].index)
    summary = {
        "TotalTasks": len(expected_ids),
        "ScheduledTasks": len(scheduled_once),
        "FinishRate": len(deadline_ok_ids) / len(expected_ids),
        "SLAViolations": sla_violations,
        "DeadlineViolations": deadline_violations,
        "TerminalViolations": terminal_violations,
        "GPUOverloadCount": int(gpu_overload.sum()),
        "ITPowerOverloadCount": int(it_overload.sum()),
        "FacilityPowerOverloadCount": int(facility_overload.sum()),
    }
    violation_table = pd.DataFrame(
        violations, columns=["Category", "TaskID", "Region", "Hour", "Detail"]
    )
    return ScheduleValidationResult(summary, violation_table, resources)

