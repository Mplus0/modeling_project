"""Build and export hourly GPU arrival demand series."""

from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.config import FORECAST_OUTPUT_DIR, METRICS_OUTPUT_DIR  # noqa: E402
from src.data_loader import load_raw_data  # noqa: E402
from src.data_validator import validate_data  # noqa: E402
from src.demand_builder import (  # noqa: E402
    aggregate_region_demand,
    aggregate_system_demand,
    build_demand_series,
)
from src.metrics import build_demand_statistics  # noqa: E402


def main() -> int:
    data = load_raw_data()
    report = validate_data(data)

    for warning in report.warnings:
        print(f"WARNING: {warning}")
    if report.errors:
        for error in report.errors:
            print(f"ERROR: {error}")
        return 1

    demand = build_demand_series(data.tasks)
    region_demand = aggregate_region_demand(demand)
    system_demand = aggregate_system_demand(demand)
    statistics = build_demand_statistics(demand)

    FORECAST_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    outputs = {
        "demand_series.csv": demand,
        "region_demand_series.csv": region_demand,
        "system_demand_series.csv": system_demand,
    }
    for filename, table in outputs.items():
        path = FORECAST_OUTPUT_DIR / filename
        table.to_csv(path, index=False, encoding="utf-8-sig")
        print(f"Saved {len(table)} rows to {path}")

    METRICS_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    statistics_path = METRICS_OUTPUT_DIR / "demand_statistics.csv"
    statistics.to_csv(statistics_path, index=False, encoding="utf-8-sig")
    print(f"Saved {len(statistics)} rows to {statistics_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
