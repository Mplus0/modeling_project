"""Generate report metrics and figures from exported model results."""

from pathlib import Path
import sys

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.config import (  # noqa: E402
    FIGURE_OUTPUT_DIR,
    FORECAST_OUTPUT_DIR,
    METRICS_OUTPUT_DIR,
    SCHEDULE_OUTPUT_DIR,
)
from src.metrics import build_schedule_metrics  # noqa: E402
from src.visualization import (  # noqa: E402
    plot_forecast_outputs,
    plot_schedule_outputs,
)


def main() -> int:
    forecast = pd.read_csv(FORECAST_OUTPUT_DIR / "forecast_2376_2399.csv")
    forecast_metrics = pd.read_csv(METRICS_OUTPUT_DIR / "forecast_metrics.csv")
    paths = plot_forecast_outputs(forecast, forecast_metrics, FIGURE_OUTPUT_DIR)

    schedule_path = SCHEDULE_OUTPUT_DIR / "task_schedule.csv"
    resource_path = SCHEDULE_OUTPUT_DIR / "region_hour_resource.csv"
    if schedule_path.exists() and resource_path.exists():
        schedule = pd.read_csv(schedule_path)
        resources = pd.read_csv(resource_path)
        schedule_metrics = build_schedule_metrics(schedule, resources)
        METRICS_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        schedule_metrics.to_csv(
            METRICS_OUTPUT_DIR / "schedule_metrics.csv",
            index=False,
            encoding="utf-8-sig",
        )
        paths.extend(plot_schedule_outputs(schedule, resources, FIGURE_OUTPUT_DIR))
    else:
        print("Schedule outputs not found; generated forecast figures only.")

    for path in paths:
        print(f"Saved {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
