"""Multi-timescale point forecast for hourly GPU arrival demand."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .config import (
    FORECAST_DAILY_LAGS,
    FORECAST_END,
    FORECAST_SHORT_WINDOW,
    FORECAST_START,
    FORECAST_WEIGHT_STEP,
    REGIONS,
    TASK_TYPES,
    TRAIN_END,
    TRAIN_START,
    VALID_END,
    VALID_START,
)
from .metrics import calculate_forecast_metrics


@dataclass(frozen=True, slots=True)
class ForecastWeights:
    alpha: float
    beta: float
    gamma: float

    def __post_init__(self) -> None:
        values = (self.alpha, self.beta, self.gamma)
        if min(values) < 0 or not np.isclose(sum(values), 1.0):
            raise ValueError("Forecast weights must be nonnegative and sum to 1")


def _build_components(
    demand: pd.DataFrame,
    history_start: int,
    history_end: int,
    forecast_start: int,
    forecast_end: int,
) -> pd.DataFrame:
    required = {"Hour", "Region", "TaskType", "GPU_Demand"}
    missing = required - set(demand.columns)
    if missing:
        raise ValueError(f"Missing demand columns: {sorted(missing)}")
    if forecast_start != history_end + 1:
        raise ValueError("Forecast horizon must start immediately after the history")
    if forecast_end - forecast_start + 1 > FORECAST_SHORT_WINDOW:
        raise ValueError("Direct forecast horizon cannot exceed 24 hours")

    columns = pd.MultiIndex.from_product(
        [REGIONS, TASK_TYPES], names=["Region", "TaskType"]
    )
    wide = demand.pivot(
        index="Hour", columns=["Region", "TaskType"], values="GPU_Demand"
    ).reindex(columns=columns)

    required_hours = range(history_start, forecast_end + 1)
    if wide.reindex(required_hours).isna().any().any():
        raise ValueError("Demand series is incomplete for the requested forecast period")

    history = wide.loc[history_start:history_end]
    if len(history) < FORECAST_DAILY_LAGS * 24:
        raise ValueError("At least seven days of history are required")

    long_term = history.mean()
    short_term = history.tail(FORECAST_SHORT_WINDOW).mean()
    pairs = list(columns)
    parts = []

    for hour in range(forecast_start, forecast_end + 1):
        lag_hours = [hour - 24 * lag for lag in range(1, FORECAST_DAILY_LAGS + 1)]
        daily_pattern = wide.loc[lag_hours].mean()
        actual = wide.loc[hour]
        parts.append(
            pd.DataFrame(
                {
                    "Hour": hour,
                    "Region": [pair[0] for pair in pairs],
                    "TaskType": [pair[1] for pair in pairs],
                    "Actual_GPU": actual.to_numpy(),
                    "LongTerm": long_term.to_numpy(),
                    "ShortTerm": short_term.to_numpy(),
                    "DailyPattern": daily_pattern.to_numpy(),
                }
            )
        )

    return pd.concat(parts, ignore_index=True)


def _apply_weights(
    components: pd.DataFrame, weights: ForecastWeights
) -> pd.DataFrame:
    result = components[["Hour", "Region", "TaskType", "Actual_GPU"]].copy()
    result["Predicted_GPU"] = (
        weights.alpha * components["LongTerm"]
        + weights.beta * components["ShortTerm"]
        + weights.gamma * components["DailyPattern"]
    )
    result["AbsoluteError"] = (
        result["Actual_GPU"] - result["Predicted_GPU"]
    ).abs()
    return result


def forecast_demand(
    demand: pd.DataFrame,
    weights: ForecastWeights,
    history_start: int = TRAIN_START,
    history_end: int = VALID_END,
    forecast_start: int = FORECAST_START,
    forecast_end: int = FORECAST_END,
) -> pd.DataFrame:
    """Forecast one direct horizon using fixed historical observations."""

    components = _build_components(
        demand, history_start, history_end, forecast_start, forecast_end
    )
    return _apply_weights(components, weights)


def select_forecast_weights(
    demand: pd.DataFrame,
    step: float = FORECAST_WEIGHT_STEP,
    history_start: int = TRAIN_START,
    history_end: int = TRAIN_END,
    forecast_start: int = VALID_START,
    forecast_end: int = VALID_END,
) -> tuple[ForecastWeights, pd.DataFrame]:
    """Select alpha, beta and gamma by validation WAPE."""

    if step <= 0:
        raise ValueError("Weight step must be positive")
    units = round(1 / step)
    if not np.isclose(units * step, 1.0):
        raise ValueError("Weight step must divide 1 exactly")

    components = _build_components(
        demand, history_start, history_end, forecast_start, forecast_end
    )
    scores = []

    for alpha_units in range(units + 1):
        for beta_units in range(units - alpha_units + 1):
            weights = ForecastWeights(
                alpha=alpha_units / units,
                beta=beta_units / units,
                gamma=(units - alpha_units - beta_units) / units,
            )
            forecast = _apply_weights(components, weights)
            metrics = calculate_forecast_metrics(
                forecast["Actual_GPU"], forecast["Predicted_GPU"]
            )
            scores.append(
                {
                    "alpha": weights.alpha,
                    "beta": weights.beta,
                    "gamma": weights.gamma,
                    **metrics,
                }
            )

    score_table = pd.DataFrame(scores)
    best = score_table.sort_values(
        ["WAPE", "MAE", "RMSE"], kind="stable"
    ).iloc[0]
    best_weights = ForecastWeights(
        float(best["alpha"]), float(best["beta"]), float(best["gamma"])
    )
    return best_weights, score_table


def build_forecast_diagnostics(
    demand: pd.DataFrame,
    baseline_weights: ForecastWeights,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Diagnose validation components and the 18 underlying series."""

    components = _build_components(
        demand, TRAIN_START, TRAIN_END, VALID_START, VALID_END
    )
    component_rows = []
    for name, weights in (
        ("LongTerm", ForecastWeights(1, 0, 0)),
        ("ShortTerm", ForecastWeights(0, 1, 0)),
        ("DailyPattern", ForecastWeights(0, 0, 1)),
    ):
        forecast = _apply_weights(components, weights)
        component_rows.append(
            {
                "Component": name,
                **calculate_forecast_metrics(
                    forecast["Actual_GPU"], forecast["Predicted_GPU"]
                ),
            }
        )

    baseline = _apply_weights(components, baseline_weights)
    history = demand[demand["Hour"].between(TRAIN_START, TRAIN_END)]
    series_rows = []
    for region in REGIONS:
        for task_type in TASK_TYPES:
            validation_part = baseline[
                baseline["Region"].eq(region)
                & baseline["TaskType"].eq(task_type)
            ]
            history_values = (
                history[
                    history["Region"].eq(region)
                    & history["TaskType"].eq(task_type)
                ]
                .sort_values("Hour")["GPU_Demand"]
                .reset_index(drop=True)
            )
            series_rows.append(
                {
                    "Region": region,
                    "TaskType": task_type,
                    **calculate_forecast_metrics(
                        validation_part["Actual_GPU"],
                        validation_part["Predicted_GPU"],
                    ),
                    "zero_ratio": float(history_values.eq(0).mean()),
                    "mean": float(history_values.mean()),
                    "std": float(history_values.std(ddof=0)),
                    "autocorrelation_lag24": float(history_values.autocorr(lag=24)),
                    "autocorrelation_lag168": float(
                        history_values.autocorr(lag=168)
                    ),
                }
            )
    return pd.DataFrame(component_rows), pd.DataFrame(series_rows)
