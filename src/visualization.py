"""Figures for the Question 1 forecast and scheduling results."""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
import numpy as np
import pandas as pd

from .config import EVALUATION_HOURS, REGIONS, TASK_TYPES


COLORS = {
    "Actual": "#1f4e79",
    "Predicted": "#e07a5f",
    "RealTimeInference": "#2a9d8f",
    "BatchInference": "#e9c46a",
    "AITraining": "#e76f51",
}


def _save(fig: plt.Figure, path: Path) -> None:
    fig.tight_layout()
    fig.savefig(path, dpi=200, bbox_inches="tight")
    plt.close(fig)


def plot_forecast_outputs(
    forecast: pd.DataFrame,
    forecast_metrics: pd.DataFrame,
    output_dir: str | Path,
) -> list[Path]:
    """Generate the four forecast figures defined in the plan."""

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []

    system = forecast.groupby("Hour", as_index=False)[
        ["Actual_GPU", "Predicted_GPU"]
    ].sum()
    fig, ax = plt.subplots(figsize=(9, 4.5))
    ax.plot(
        system["Hour"],
        system["Actual_GPU"],
        marker="o",
        label="Actual",
        color=COLORS["Actual"],
    )
    ax.plot(
        system["Hour"],
        system["Predicted_GPU"],
        marker="o",
        label="Predicted",
        color=COLORS["Predicted"],
    )
    ax.set(title="System GPU demand", xlabel="Hour", ylabel="Equivalent GPU")
    ax.legend()
    path = output_dir / "01_system_gpu_demand_actual_vs_predicted.png"
    _save(fig, path)
    paths.append(path)

    region_data = forecast.groupby(["Hour", "Region"], as_index=False)[
        ["Actual_GPU", "Predicted_GPU"]
    ].sum()
    fig, axes = plt.subplots(2, 3, figsize=(13, 7), sharex=True)
    for ax, region in zip(axes.flat, REGIONS):
        selected = region_data[region_data["Region"].eq(region)]
        ax.plot(
            selected["Hour"], selected["Actual_GPU"], color=COLORS["Actual"], label="Actual"
        )
        ax.plot(
            selected["Hour"],
            selected["Predicted_GPU"],
            color=COLORS["Predicted"],
            label="Predicted",
        )
        ax.set_title(region)
    axes[0, 0].legend()
    fig.supxlabel("Hour")
    fig.supylabel("Equivalent GPU")
    path = output_dir / "02_region_forecast_comparison.png"
    _save(fig, path)
    paths.append(path)

    task_data = forecast.groupby(["Hour", "TaskType"], as_index=False)[
        ["Actual_GPU", "Predicted_GPU"]
    ].sum()
    fig, axes = plt.subplots(1, 3, figsize=(14, 4), sharex=True)
    for ax, task_type in zip(axes, TASK_TYPES):
        selected = task_data[task_data["TaskType"].eq(task_type)]
        ax.plot(
            selected["Hour"], selected["Actual_GPU"], color=COLORS["Actual"], label="Actual"
        )
        ax.plot(
            selected["Hour"],
            selected["Predicted_GPU"],
            color=COLORS["Predicted"],
            label="Predicted",
        )
        ax.set_title(task_type)
    axes[0].legend()
    fig.supxlabel("Hour")
    fig.supylabel("Equivalent GPU")
    path = output_dir / "03_tasktype_forecast_comparison.png"
    _save(fig, path)
    paths.append(path)

    by_region = forecast_metrics[forecast_metrics["Level"].eq("region")]
    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.bar(by_region["Region"], by_region["WAPE"] * 100, color="#4c78a8")
    ax.set(title="Forecast WAPE by region", xlabel="Region", ylabel="WAPE (%)")
    path = output_dir / "04_forecast_error_by_region.png"
    _save(fig, path)
    paths.append(path)
    return paths


def plot_schedule_outputs(
    schedule: pd.DataFrame,
    resources: pd.DataFrame,
    output_dir: str | Path,
) -> list[Path]:
    """Generate the six scheduling figures defined in the plan."""

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    main_resources = resources[resources["Hour"].isin(EVALUATION_HOURS)]

    fig, ax = plt.subplots(figsize=(12, 5.5))
    for region_index, region in enumerate(REGIONS):
        selected = schedule[schedule["TargetRegion"].eq(region)].reset_index(drop=True)
        offsets = np.linspace(-0.32, 0.32, max(len(selected), 2))[: len(selected)]
        for offset, task in zip(offsets, selected.itertuples(index=False)):
            ax.plot(
                [task.StartHour, task.FinishHour],
                [region_index + offset, region_index + offset],
                color=COLORS[task.TaskType],
                linewidth=1.5,
                alpha=0.55,
            )
    ax.set_yticks(range(len(REGIONS)), REGIONS)
    ax.set(title="Task schedule", xlabel="Hour", ylabel="Target region")
    ax.legend(
        handles=[Line2D([0], [0], color=COLORS[t], lw=3, label=t) for t in TASK_TYPES],
        loc="upper left",
        ncols=3,
    )
    path = output_dir / "05_task_gantt.png"
    _save(fig, path)
    paths.append(path)

    fig, ax = plt.subplots(figsize=(10, 5))
    for region in REGIONS:
        selected = main_resources[main_resources["Region"].eq(region)]
        ax.plot(
            selected["Hour"],
            selected["GPU_Utilization"] * 100,
            marker="o",
            label=region,
        )
    ax.set(title="GPU utilization by region", xlabel="Hour", ylabel="Utilization (%)")
    ax.legend(ncols=3)
    path = output_dir / "06_gpu_utilization_by_region.png"
    _save(fig, path)
    paths.append(path)

    matrix = main_resources.pivot(
        index="Region", columns="Hour", values="GPU_Utilization"
    ).reindex(REGIONS)
    fig, ax = plt.subplots(figsize=(12, 4))
    image = ax.imshow(matrix.to_numpy() * 100, aspect="auto", cmap="YlOrRd")
    ax.set_yticks(range(len(REGIONS)), REGIONS)
    ax.set_xticks(range(len(matrix.columns)), matrix.columns, rotation=90)
    ax.set(title="GPU utilization heatmap", xlabel="Hour", ylabel="Region")
    fig.colorbar(image, ax=ax, label="Utilization (%)")
    path = output_dir / "07_gpu_utilization_heatmap.png"
    _save(fig, path)
    paths.append(path)

    migration = pd.crosstab(
        schedule["SourceRegion"], schedule["TargetRegion"]
    ).reindex(index=REGIONS, columns=REGIONS, fill_value=0)
    fig, ax = plt.subplots(figsize=(6.5, 5.5))
    image = ax.imshow(migration.to_numpy(), cmap="Blues")
    ax.set_xticks(range(len(REGIONS)), REGIONS, rotation=45, ha="right")
    ax.set_yticks(range(len(REGIONS)), REGIONS)
    ax.set(title="Task migration matrix", xlabel="Target region", ylabel="Source region")
    for i in range(len(REGIONS)):
        for j in range(len(REGIONS)):
            ax.text(j, i, int(migration.iloc[i, j]), ha="center", va="center")
    fig.colorbar(image, ax=ax, label="Task count")
    path = output_dir / "08_task_migration_matrix.png"
    _save(fig, path)
    paths.append(path)

    fig, ax = plt.subplots(figsize=(9, 4.5))
    for task_type in TASK_TYPES:
        waits = schedule.loc[schedule["TaskType"].eq(task_type), "WaitHour"]
        ax.hist(
            waits,
            bins=20,
            alpha=0.55,
            label=task_type,
            color=COLORS[task_type],
        )
    ax.set(title="Task waiting time", xlabel="Wait (hour)", ylabel="Task count")
    ax.legend()
    path = output_dir / "09_wait_time_distribution.png"
    _save(fig, path)
    paths.append(path)

    fig, ax = plt.subplots(figsize=(10, 5))
    for region in REGIONS:
        selected = main_resources[main_resources["Region"].eq(region)]
        utilization = selected["Total_IT_Power_MW"] / selected["Max_IT_Power_MW"]
        ax.plot(selected["Hour"], utilization * 100, marker="o", label=region)
    ax.set(
        title="IT power utilization by region",
        xlabel="Hour",
        ylabel="Utilization (%)",
    )
    ax.legend(ncols=3)
    path = output_dir / "10_region_power_utilization.png"
    _save(fig, path)
    paths.append(path)
    return paths

