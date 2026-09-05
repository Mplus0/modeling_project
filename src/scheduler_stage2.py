"""Stage 2 peak-utilization optimization built on the stage-1 model."""

from __future__ import annotations

from collections.abc import Iterable

import pandas as pd
from pyscipopt import Variable

from .config import REGIONS, RESOURCE_HOURS
from .scheduler_stage1 import ScheduleModel, SolverSummary, summarize_solution


def configure_stage2(
    schedule_model: ScheduleModel,
    gpu_info: pd.DataFrame,
    stage1_objective: float,
    delta: float,
    peak_hours: Iterable[int],
) -> Variable:
    """Add the service-quality bound and peak-utilization objective."""

    if schedule_model.wait_objective is None:
        raise ValueError("Stage 1 waiting objective has not been built")
    if delta < 0:
        raise ValueError("delta must be nonnegative")

    hours = tuple(dict.fromkeys(int(hour) for hour in peak_hours))
    invalid_hours = sorted(set(hours) - set(RESOURCE_HOURS))
    if not hours or invalid_hours:
        raise ValueError(f"Invalid peak_hours: {invalid_hours or 'empty'}")

    model = schedule_model.model
    best_solution = model.getBestSol()
    if best_solution is None:
        raise RuntimeError("Stage 1 has no solution for the stage-2 warm start")
    warm_values = {
        key: model.getSolVal(best_solution, variable)
        for key, variable in schedule_model.x.items()
    }
    available_gpu = gpu_info.set_index("Region")["Available_GPU"].to_dict()
    warm_peak = max(
        model.getSolVal(best_solution, schedule_model.gpu_used[(region, hour)])
        / available_gpu[region]
        for region in REGIONS
        for hour in hours
    )
    model.freeTransform()
    model.addCons(
        schedule_model.wait_objective <= (1 + delta) * stage1_objective,
        name="stage1_service_bound",
    )

    u_max = model.addVar(lb=0, vtype="C", name="U_max")
    for region in REGIONS:
        for hour in hours:
            model.addCons(
                schedule_model.gpu_used[(region, hour)]
                <= available_gpu[region] * u_max,
                name=f"peak_utilization[{region},{hour}]",
            )

    warm_start = model.createSol()
    for key, variable in schedule_model.x.items():
        model.setSolVal(warm_start, variable, warm_values[key])
    model.setSolVal(warm_start, u_max, warm_peak)
    model.addSol(warm_start)
    model.setObjective(u_max, sense="minimize")
    return u_max


def solve_stage2(
    schedule_model: ScheduleModel,
    time_limit: float | None = None,
    mip_gap: float | None = None,
    log_file: str | None = None,
) -> SolverSummary:
    """Solve the configured stage-2 model."""

    model = schedule_model.model
    if time_limit is not None:
        model.setRealParam("limits/time", time_limit)
    if mip_gap is not None:
        model.setRealParam("limits/gap", mip_gap)
    if log_file is not None:
        model.setLogfile(log_file)
    model.optimize()
    return summarize_solution(model)
