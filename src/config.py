"""Project-wide constants for Question 1.

All hour bounds are inclusive unless their name explicitly says otherwise.
"""

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_DATA_DIR = PROJECT_ROOT / "data" / "raw"
OUTPUT_DIR = PROJECT_ROOT / "outputs"
FORECAST_OUTPUT_DIR = OUTPUT_DIR / "forecast"
METRICS_OUTPUT_DIR = OUTPUT_DIR / "metrics"

REGIONS: tuple[str, ...] = tuple(f"Region{letter}" for letter in "ABCDEF")
TASK_TYPES: tuple[str, ...] = (
    "RealTimeInference",
    "BatchInference",
    "AITraining",
)

TRAIN_START = 0
TRAIN_END = 2351
VALID_START = 2352
VALID_END = 2375
FORECAST_START = 2376
FORECAST_END = 2399

SCHEDULE_ARRIVAL_START = 2376
SCHEDULE_ARRIVAL_END = 2399
TERMINAL_TIME = 2406

# A task may occupy [2405, 2406), but it must not occupy hour 2406.
RESOURCE_HOURS: range = range(SCHEDULE_ARRIVAL_START, TERMINAL_TIME)
EVALUATION_HOURS: range = range(FORECAST_START, FORECAST_END + 1)
DEMAND_HOURS: range = range(TRAIN_START, FORECAST_END + 1)

FORECAST_WEIGHT_STEP = 0.05
FORECAST_SHORT_WINDOW = 24
FORECAST_DAILY_LAGS = 7


RAW_DATA_FILES: dict[str, str] = {
    "tasks": "workload_trace.xlsx",
    "gpu_info": "GPU_information.xlsx",
    "latency": "network_latency.xlsx",
    "power_map": "power_mapping.xlsx",
    "region_time": "region_time_data.xlsx",
    "storage": "storage_information.xlsx",
}

RAW_DATA_SHEETS: dict[str, str] = {
    "tasks": "Sheet1",
    "gpu_info": "GPU中心基础情况",
    "latency": "network_latency",
    "power_map": "任务功率映射",
    "region_time": "region_time_data",
    "storage": "storage_information",
}
