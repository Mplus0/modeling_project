"""Select forecast weights and export the Question 1 point forecast."""

from pathlib import Path
import json
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.config import (  # noqa: E402
    FORECAST_OUTPUT_DIR,
    FORECAST_WEIGHT_STEP,
    METRICS_OUTPUT_DIR,
    TRAIN_END,
    TRAIN_START,
    VALID_END,
    VALID_START,
)
from src.data_loader import load_raw_data  # noqa: E402
from src.data_validator import validate_data  # noqa: E402
from src.demand_builder import build_demand_series  # noqa: E402
from src.forecast import forecast_demand, select_forecast_weights  # noqa: E402
from src.metrics import (  # noqa: E402
    build_forecast_metrics,
    calculate_forecast_metrics,
)


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
    weights, search_scores = select_forecast_weights(demand)

    validation_forecast = forecast_demand(
        demand,
        weights,
        history_start=TRAIN_START,
        history_end=TRAIN_END,
        forecast_start=VALID_START,
        forecast_end=VALID_END,
    )
    validation_metrics = calculate_forecast_metrics(
        validation_forecast["Actual_GPU"],
        validation_forecast["Predicted_GPU"],
    )

    final_forecast = forecast_demand(demand, weights)
    final_metrics = build_forecast_metrics(final_forecast)

    FORECAST_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    METRICS_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    forecast_path = FORECAST_OUTPUT_DIR / "forecast_2376_2399.csv"
    search_path = FORECAST_OUTPUT_DIR / "validation_weight_search.csv"
    parameters_path = FORECAST_OUTPUT_DIR / "forecast_parameters.json"
    metrics_path = METRICS_OUTPUT_DIR / "forecast_metrics.csv"

    final_forecast.to_csv(forecast_path, index=False, encoding="utf-8-sig")
    search_scores.to_csv(search_path, index=False, encoding="utf-8-sig")
    final_metrics.to_csv(metrics_path, index=False, encoding="utf-8-sig")

    parameters = {
        "alpha": weights.alpha,
        "beta": weights.beta,
        "gamma": weights.gamma,
        "weight_search_step": FORECAST_WEIGHT_STEP,
        "validation_method": "direct_24_hour",
        "validation_WAPE": validation_metrics["WAPE"],
        "validation_MAE": validation_metrics["MAE"],
        "validation_RMSE": validation_metrics["RMSE"],
    }
    parameters_path.write_text(
        json.dumps(parameters, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(f"Selected weights: {weights}")
    print(f"Validation metrics: {validation_metrics}")
    for path in (forecast_path, search_path, parameters_path, metrics_path):
        print(f"Saved {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

