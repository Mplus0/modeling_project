"""Stage 1 scheduling model, built incrementally from the minimal MILP."""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd
from pyscipopt import Expr, Model, Variable, quicksum

from .config import REGIONS, RESOURCE_HOURS
from .feasible_domain import FeasibleDomains
from .overlap import ActiveOptions, OverlapValues


@dataclass(slots=True)
class ScheduleModel:
    model: Model
    x: dict[tuple[int, str, int], Variable]
    gpu_used: dict[tuple[str, int], Expr] = field(default_factory=dict)
    ai_it_power: dict[tuple[str, int], Expr] = field(default_factory=dict)
    wait_objective: Expr | None = None


@dataclass(frozen=True, slots=True)
class SolverSummary:
    status: str
    status_name: str
    objective: float | None
    runtime: float
    mip_gap: float | None
    solution_count: int

    def as_dict(self) -> dict[str, int | float | str | None]:
        return {
            "status": self.status,
            "status_name": self.status_name,
            "objective": self.objective,
            "runtime": self.runtime,
            "mip_gap": self.mip_gap,
            "solution_count": self.solution_count,
        }


def build_minimal_schedule_model(
    tasks: pd.DataFrame,
    gpu_info: pd.DataFrame,
    feasible_domains: FeasibleDomains,
    overlaps: OverlapValues,
    active_options: ActiveOptions,
) -> ScheduleModel:
    """Build assignment variables, unique-choice and GPU-capacity constraints."""

    model = Model("question1_stage1")
    option_keys = [
        (task_id, region, start)
        for task_id, options in feasible_domains.items()
        for region, start in options
    ]
    x = {
        key: model.addVar(vtype="B", name=f"x[{key[0]},{key[1]},{key[2]}]")
        for key in option_keys
    }

    for task_id, options in feasible_domains.items():
        model.addCons(
            quicksum(x[task_id, region, start] for region, start in options) == 1,
            name=f"assign[{task_id}]",
        )

    gpu_demand = tasks.set_index("TaskID")["GPU_Demand"].to_dict()
    available_gpu = gpu_info.set_index("Region")["Available_GPU"].to_dict()
    gpu_used: dict[tuple[str, int], Expr] = {}

    for region in REGIONS:
        for hour in RESOURCE_HOURS:
            active = active_options.get((region, hour), [])
            usage = quicksum(
                gpu_demand[task_id]
                * overlaps[(task_id, start, hour)]
                * x[task_id, option_region, start]
                for task_id, option_region, start in active
            )
            gpu_used[(region, hour)] = usage
            model.addCons(
                usage <= available_gpu[region],
                name=f"gpu_capacity[{region},{hour}]",
            )

    return ScheduleModel(model=model, x=x, gpu_used=gpu_used)


def add_power_constraints(
    schedule_model: ScheduleModel,
    tasks: pd.DataFrame,
    gpu_info: pd.DataFrame,
    power_map: pd.DataFrame,
    region_time: pd.DataFrame,
    overlaps: OverlapValues,
    active_options: ActiveOptions,
) -> ScheduleModel:
    """Add IT-side and facility-side power constraints."""

    model = schedule_model.model
    x = schedule_model.x
    gpu_demand = tasks.set_index("TaskID")["GPU_Demand"].to_dict()
    task_type = tasks.set_index("TaskID")["TaskType"].to_dict()
    unit_power = power_map.set_index("TaskType")[
        "GPU_Power_MW_per_EquivalentGPU"
    ].to_dict()
    non_ai_load = region_time.set_index(["Region", "Hour"])[
        "NonAI_IT_Load_MW"
    ].to_dict()
    gpu_parameters = gpu_info.set_index("Region")

    for region in REGIONS:
        max_it_power = gpu_parameters.loc[region, "Max_IT_Power_MW"]
        pue = gpu_parameters.loc[region, "PUE"]
        max_facility_power = gpu_parameters.loc[region, "Max_Facility_Power_MW"]

        for hour in RESOURCE_HOURS:
            active = active_options.get((region, hour), [])
            ai_power = quicksum(
                unit_power[task_type[task_id]]
                * gpu_demand[task_id]
                * overlaps[(task_id, start, hour)]
                * x[task_id, option_region, start]
                for task_id, option_region, start in active
            )
            schedule_model.ai_it_power[(region, hour)] = ai_power
            total_it_power = non_ai_load[(region, hour)] + ai_power

            model.addCons(
                total_it_power <= max_it_power,
                name=f"it_power[{region},{hour}]",
            )
            model.addCons(
                pue * total_it_power <= max_facility_power,
                name=f"facility_power[{region},{hour}]",
            )

    return schedule_model


def add_waiting_objective(
    schedule_model: ScheduleModel,
    tasks: pd.DataFrame,
    feasible_domains: FeasibleDomains,
    epsilon: float,
) -> ScheduleModel:
    """Set the stage-1 normalized waiting-time objective."""

    if epsilon <= 0:
        raise ValueError("epsilon must be positive")

    task_parameters = tasks.set_index("TaskID")[
        ["ArrivalHour", "LatestFinishHour", "DurationHour"]
    ].to_dict("index")
    terms = []
    for task_id, options in feasible_domains.items():
        values = task_parameters[task_id]
        max_delay = (
            values["LatestFinishHour"]
            - values["ArrivalHour"]
            - values["DurationHour"]
        )
        denominator = max_delay + epsilon
        if denominator <= 0:
            raise ValueError(f"TaskID={task_id} has nonpositive waiting denominator")
        terms.extend(
            (start - values["ArrivalHour"])
            / denominator
            * schedule_model.x[task_id, region, start]
            for region, start in options
        )

    schedule_model.wait_objective = quicksum(terms)
    schedule_model.model.setObjective(
        schedule_model.wait_objective, sense="minimize"
    )
    return schedule_model


def build_stage1_model(
    tasks: pd.DataFrame,
    gpu_info: pd.DataFrame,
    power_map: pd.DataFrame,
    region_time: pd.DataFrame,
    feasible_domains: FeasibleDomains,
    overlaps: OverlapValues,
    active_options: ActiveOptions,
    epsilon: float,
) -> ScheduleModel:
    """Build the complete stage-1 model without solving it."""

    schedule_model = build_minimal_schedule_model(
        tasks, gpu_info, feasible_domains, overlaps, active_options
    )
    add_power_constraints(
        schedule_model,
        tasks,
        gpu_info,
        power_map,
        region_time,
        overlaps,
        active_options,
    )
    return add_waiting_objective(schedule_model, tasks, feasible_domains, epsilon)


def solve_stage1(
    schedule_model: ScheduleModel,
    time_limit: float | None = None,
    mip_gap: float | None = None,
    log_file: str | None = None,
) -> SolverSummary:
    """Solve stage 1 and return a serializable solver summary."""

    model = schedule_model.model
    if time_limit is not None:
        model.setRealParam("limits/time", time_limit)
    if mip_gap is not None:
        model.setRealParam("limits/gap", mip_gap)
    if log_file is not None:
        model.setLogfile(log_file)
    model.optimize()
    return summarize_solution(model)


def summarize_solution(model: Model) -> SolverSummary:
    """Read status and incumbent information from a solved SCIP model."""

    status = str(model.getStatus())
    solution_count = int(model.getNSols())
    has_solution = solution_count > 0
    return SolverSummary(
        status=status,
        status_name=status.upper(),
        objective=float(model.getObjVal()) if has_solution else None,
        runtime=float(model.getSolvingTime()),
        mip_gap=float(model.getGap()) if has_solution else None,
        solution_count=solution_count,
    )


def decode_schedule_solution(
    tasks: pd.DataFrame,
    latency: pd.DataFrame,
    schedule_model: ScheduleModel,
    threshold: float = 0.5,
) -> pd.DataFrame:
    """Decode the selected binary options into the task schedule table."""

    solution = schedule_model.model.getBestSol()
    if solution is None:
        raise RuntimeError("The model has no solution to decode")

    chosen: dict[int, tuple[str, int]] = {}
    for (task_id, region, start), variable in schedule_model.x.items():
        value = schedule_model.model.getSolVal(solution, variable)
        if value > threshold:
            if task_id in chosen:
                raise RuntimeError(f"TaskID={task_id} has multiple selected options")
            chosen[task_id] = (region, start)

    expected_ids = set(tasks["TaskID"].astype(int))
    if set(chosen) != expected_ids:
        missing = sorted(expected_ids - set(chosen))
        raise RuntimeError(f"Missing selected options for TaskID: {missing[:10]}")

    latency_map = latency.set_index(["FromRegion", "ToRegion"])[
        "NetworkLatency_ms"
    ].to_dict()
    rows = []
    for task in tasks.sort_values("TaskID").itertuples(index=False):
        target_region, start = chosen[int(task.TaskID)]
        duration = float(task.DurationHour)
        rows.append(
            {
                "TaskID": int(task.TaskID),
                "TaskType": task.TaskType,
                "SourceRegion": task.SourceRegion,
                "TargetRegion": target_region,
                "ArrivalHour": int(task.ArrivalHour),
                "StartHour": int(start),
                "DurationHour": duration,
                "FinishHour": start + duration,
                "GPU_Demand": float(task.GPU_Demand),
                "MaxLatency_ms": float(task.MaxLatency_ms),
                "ActualLatency_ms": float(
                    latency_map[(task.SourceRegion, target_region)]
                ),
                "WaitHour": float(start - task.ArrivalHour),
                "LatestFinishHour": float(task.LatestFinishHour),
            }
        )
    return pd.DataFrame(rows)
