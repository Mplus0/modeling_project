"""Consistency checks for the raw competition data."""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from .config import REGIONS, TASK_TYPES, TERMINAL_TIME
from .data_loader import RawDataBundle


@dataclass(slots=True)
class ValidationReport:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return not self.errors

    def raise_for_errors(self) -> None:
        if self.errors:
            details = "\n".join(f"- {message}" for message in self.errors)
            raise ValueError(f"Raw data validation failed:\n{details}")


REQUIRED_COLUMNS = {
    "tasks": {
        "TaskID",
        "TaskType",
        "ArrivalHour",
        "GPU_Demand",
        "EstimatedDuration_min",
        "DelaySensitivity",
        "SourceRegion",
        "MaxLatency_ms",
        "LatestFinishHour",
        "EarliestStartHour",
        "ExecutionMode",
    },
    "gpu_info": {
        "Region",
        "Total_GPU",
        "Available_GPU",
        "Max_IT_Power_MW",
        "PUE",
        "Max_Facility_Power_MW",
    },
    "latency": {"FromRegion", "ToRegion", "NetworkLatency_ms"},
    "power_map": {"TaskType", "GPU_Power_MW_per_EquivalentGPU"},
    "region_time": {
        "Hour",
        "Region",
        "NonAI_IT_Load_MW",
        "GPU_Utilization_Percent",
    },
    "storage": {"Region"},
}


def _check_required_columns(
    tables: dict[str, pd.DataFrame], report: ValidationReport
) -> set[str]:
    invalid_tables: set[str] = set()
    for name, required in REQUIRED_COLUMNS.items():
        missing = sorted(required - set(tables[name].columns))
        if missing:
            report.errors.append(f"{name}: missing columns {missing}")
            invalid_tables.add(name)
    return invalid_tables


def _check_region_table(
    table: pd.DataFrame,
    table_name: str,
    report: ValidationReport,
) -> None:
    if table["Region"].duplicated().any():
        report.errors.append(f"{table_name}: Region contains duplicates")
    actual = set(table["Region"].dropna())
    expected = set(REGIONS)
    if actual != expected:
        report.errors.append(
            f"{table_name}: Region mismatch; missing={sorted(expected - actual)}, "
            f"unexpected={sorted(actual - expected)}"
        )


def _validate_tasks(tasks: pd.DataFrame, report: ValidationReport) -> None:
    if tasks["TaskID"].isna().any():
        report.errors.append("tasks: TaskID contains missing values")
    if tasks["TaskID"].duplicated().any():
        report.errors.append("tasks: TaskID must be unique")

    checks = {
        "ArrivalHour must be between 0 and 2399": ~tasks["ArrivalHour"].between(0, 2399),
        "GPU_Demand must be positive": tasks["GPU_Demand"] <= 0,
        "EstimatedDuration_min must be positive": tasks["EstimatedDuration_min"] <= 0,
        "MaxLatency_ms must be nonnegative": tasks["MaxLatency_ms"] < 0,
        "EarliestStartHour cannot precede ArrivalHour": (
            tasks["EarliestStartHour"] < tasks["ArrivalHour"]
        ),
        "EarliestStartHour cannot exceed LatestFinishHour": (
            tasks["EarliestStartHour"] > tasks["LatestFinishHour"]
        ),
        "a task cannot finish by its deadline from EarliestStartHour": (
            tasks["EarliestStartHour"]
            + tasks["EstimatedDuration_min"] / 60
            > tasks["LatestFinishHour"] + 1e-9
        ),
        f"LatestFinishHour cannot exceed terminal time {TERMINAL_TIME}": (
            tasks["LatestFinishHour"] > TERMINAL_TIME
        ),
    }
    for message, mask in checks.items():
        count = int(mask.fillna(True).sum())
        if count:
            report.errors.append(f"tasks: {message} ({count} rows)")

    invalid_types = sorted(set(tasks["TaskType"].dropna()) - set(TASK_TYPES))
    if invalid_types or tasks["TaskType"].isna().any():
        report.errors.append(f"tasks: invalid TaskType values {invalid_types}")

    invalid_regions = sorted(set(tasks["SourceRegion"].dropna()) - set(REGIONS))
    if invalid_regions or tasks["SourceRegion"].isna().any():
        report.errors.append(f"tasks: invalid SourceRegion values {invalid_regions}")

    if not tasks["ExecutionMode"].eq("NonPreemptive").all():
        count = int((~tasks["ExecutionMode"].eq("NonPreemptive")).sum())
        report.errors.append(f"tasks: ExecutionMode is not NonPreemptive ({count} rows)")

    expected_sensitivity = {
        "RealTimeInference": "High",
        "BatchInference": "Medium",
        "AITraining": "Low",
    }
    mismatch = tasks["DelaySensitivity"].ne(
        tasks["TaskType"].map(expected_sensitivity)
    )
    if mismatch.any():
        report.errors.append(
            f"tasks: TaskType and DelaySensitivity mismatch ({int(mismatch.sum())} rows)"
        )


def _validate_gpu_info(gpu_info: pd.DataFrame, report: ValidationReport) -> None:
    _check_region_table(gpu_info, "gpu_info", report)
    for column in (
        "Total_GPU",
        "Available_GPU",
        "Max_IT_Power_MW",
        "PUE",
        "Max_Facility_Power_MW",
    ):
        count = int((gpu_info[column].isna() | (gpu_info[column] <= 0)).sum())
        if count:
            report.errors.append(f"gpu_info: {column} must be positive ({count} rows)")

    exceeds_total = gpu_info["Available_GPU"] > gpu_info["Total_GPU"]
    if exceeds_total.any():
        report.errors.append(
            "gpu_info: Available_GPU exceeds Total_GPU "
            f"({int(exceeds_total.sum())} rows)"
        )


def _validate_latency(latency: pd.DataFrame, report: ValidationReport) -> None:
    key = ["FromRegion", "ToRegion"]
    duplicates = int(latency.duplicated(key).sum())
    if duplicates:
        report.errors.append(f"latency: duplicate region pairs ({duplicates} rows)")

    actual_pairs = set(map(tuple, latency[key].dropna().to_numpy()))
    expected_pairs = {(source, target) for source in REGIONS for target in REGIONS}
    if actual_pairs != expected_pairs:
        report.errors.append(
            "latency: incomplete 6 x 6 region pairs; "
            f"missing={sorted(expected_pairs - actual_pairs)}, "
            f"unexpected={sorted(actual_pairs - expected_pairs)}"
        )

    invalid = latency["NetworkLatency_ms"].isna() | (
        latency["NetworkLatency_ms"] < 0
    )
    if invalid.any():
        report.errors.append(
            f"latency: NetworkLatency_ms must be nonnegative ({int(invalid.sum())} rows)"
        )


def _validate_power_map(power_map: pd.DataFrame, report: ValidationReport) -> None:
    if power_map["TaskType"].duplicated().any():
        report.errors.append("power_map: TaskType contains duplicates")
    actual = set(power_map["TaskType"].dropna())
    expected = set(TASK_TYPES)
    if actual != expected:
        report.errors.append(
            f"power_map: TaskType mismatch; missing={sorted(expected - actual)}, "
            f"unexpected={sorted(actual - expected)}"
        )
    invalid = power_map["GPU_Power_MW_per_EquivalentGPU"].isna() | (
        power_map["GPU_Power_MW_per_EquivalentGPU"] <= 0
    )
    if invalid.any():
        report.errors.append(
            "power_map: GPU power mapping must be positive "
            f"({int(invalid.sum())} rows)"
        )


def _validate_region_time(
    region_time: pd.DataFrame, report: ValidationReport
) -> None:
    key = ["Region", "Hour"]
    duplicates = int(region_time.duplicated(key).sum())
    if duplicates:
        report.errors.append(f"region_time: duplicate Region-Hour rows ({duplicates})")

    actual_pairs = set(map(tuple, region_time[key].dropna().to_numpy()))
    expected_pairs = {
        (region, hour)
        for region in REGIONS
        for hour in range(TERMINAL_TIME + 1)
    }
    if actual_pairs != expected_pairs:
        report.errors.append(
            "region_time: incomplete Region-Hour grid; "
            f"missing={len(expected_pairs - actual_pairs)}, "
            f"unexpected={len(actual_pairs - expected_pairs)}"
        )

    invalid_load = region_time["NonAI_IT_Load_MW"].isna() | (
        region_time["NonAI_IT_Load_MW"] < 0
    )
    if invalid_load.any():
        report.errors.append(
            "region_time: NonAI_IT_Load_MW must be nonnegative "
            f"({int(invalid_load.sum())} rows)"
        )

    baseline_overload = region_time["GPU_Utilization_Percent"] > 100
    if baseline_overload.any():
        overloaded = region_time.loc[
            baseline_overload, ["Hour", "Region", "GPU_Utilization_Percent"]
        ].copy()
        overloaded["ExcelRow"] = overloaded.index + 2
        overloaded = overloaded.sort_values(
            "GPU_Utilization_Percent", ascending=False
        )
        examples = "; ".join(
            f"row {row.ExcelRow}: Hour={row.Hour}, Region={row.Region}, "
            f"value={row.GPU_Utilization_Percent:.6f}%"
            for row in overloaded.head(5).itertuples(index=False)
        )
        report.warnings.append(
            "region_time: baseline GPU_Utilization_Percent exceeds 100%; "
            f"count={len(overloaded)}, "
            f"max={overloaded['GPU_Utilization_Percent'].max():.6f}%; "
            f"examples=[{examples}]. This is a baseline result field and is not "
            "used as a hard GPU-capacity input."
        )


def validate_data(data: RawDataBundle) -> ValidationReport:
    """Validate all raw tables without modifying them."""

    report = ValidationReport()
    tables = data.as_dict()
    invalid_tables = _check_required_columns(tables, report)

    if "tasks" not in invalid_tables:
        _validate_tasks(data.tasks, report)
    if "gpu_info" not in invalid_tables:
        _validate_gpu_info(data.gpu_info, report)
    if "latency" not in invalid_tables:
        _validate_latency(data.latency, report)
    if "power_map" not in invalid_tables:
        _validate_power_map(data.power_map, report)
    if "region_time" not in invalid_tables:
        _validate_region_time(data.region_time, report)
    if "storage" not in invalid_tables:
        _check_region_table(data.storage, "storage", report)

    return report

