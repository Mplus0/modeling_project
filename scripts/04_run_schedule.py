"""Solve both scheduling stages and export validated task/resource tables."""

from argparse import ArgumentParser, Namespace
import json
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.config import (  # noqa: E402
    EVALUATION_HOURS,
    LOG_OUTPUT_DIR,
    METRICS_OUTPUT_DIR,
    PEAK_HOUR_SCOPE,
    RESOURCE_HOURS,
    SCHEDULE_OUTPUT_DIR,
    SERVICE_DEGRADATION_DELTA,
    WAIT_NORMALIZATION_EPSILON,
)
from src.data_loader import load_raw_data  # noqa: E402
from src.data_validator import validate_data  # noqa: E402
from src.feasible_domain import (  # noqa: E402
    build_feasible_domains,
    select_schedule_tasks,
)
from src.overlap import precompute_overlaps  # noqa: E402
from src.result_validator import validate_schedule  # noqa: E402
from src.scheduler_stage1 import (  # noqa: E402
    build_stage1_model,
    decode_schedule_solution,
    solve_stage1,
)
from src.scheduler_stage2 import configure_stage2, solve_stage2  # noqa: E402


def parse_args() -> Namespace:
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--epsilon", type=float, default=WAIT_NORMALIZATION_EPSILON)
    parser.add_argument("--delta", type=float, default=SERVICE_DEGRADATION_DELTA)
    parser.add_argument(
        "--peak-hours",
        choices=("evaluation", "resource"),
        default=PEAK_HOUR_SCOPE,
        help="evaluation=2376-2399; resource=2376-2405",
    )
    parser.add_argument("--time-limit", type=float)
    parser.add_argument("--mip-gap", type=float)
    args = parser.parse_args()
    if args.epsilon is None or args.delta is None or args.peak_hours is None:
        parser.error("epsilon, delta and peak-hours require modeling-team confirmation")
    return args


def write_json(path: Path, values: dict) -> None:
    path.write_text(
        json.dumps(values, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def main() -> int:
    args = parse_args()
    data = load_raw_data()
    report = validate_data(data)
    for warning in report.warnings:
        print(f"WARNING: {warning}")
    report.raise_for_errors()

    tasks = select_schedule_tasks(data.tasks)
    feasible_domains = build_feasible_domains(tasks, data.latency)
    overlaps, active_options = precompute_overlaps(tasks, feasible_domains)
    option_count = sum(map(len, feasible_domains.values()))
    print(f"Schedule tasks: {len(tasks)}")
    print(f"Feasible options: {option_count}")

    SCHEDULE_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    METRICS_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    LOG_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    schedule_model = build_stage1_model(
        tasks,
        data.gpu_info,
        data.power_map,
        data.region_time,
        feasible_domains,
        overlaps,
        active_options,
        args.epsilon,
    )
    stage1_summary = solve_stage1(
        schedule_model,
        time_limit=args.time_limit,
        mip_gap=args.mip_gap,
        log_file=str(LOG_OUTPUT_DIR / "stage1_solver.log"),
    )
    print(f"Stage 1: {stage1_summary.status_name}")
    if stage1_summary.status != "optimal":
        raise RuntimeError("Stage 1 must be optimal before stage 2 is configured")

    stage1_schedule = decode_schedule_solution(tasks, data.latency, schedule_model)
    stage1_schedule.to_csv(
        SCHEDULE_OUTPUT_DIR / "stage1_solution.csv",
        index=False,
        encoding="utf-8-sig",
    )
    write_json(
        SCHEDULE_OUTPUT_DIR / "stage1_summary.json",
        {**stage1_summary.as_dict(), "epsilon": args.epsilon},
    )

    peak_hours = EVALUATION_HOURS if args.peak_hours == "evaluation" else RESOURCE_HOURS
    configure_stage2(
        schedule_model,
        data.gpu_info,
        stage1_summary.objective,
        args.delta,
        peak_hours,
    )
    stage2_summary = solve_stage2(
        schedule_model,
        time_limit=args.time_limit,
        mip_gap=args.mip_gap,
        log_file=str(LOG_OUTPUT_DIR / "stage2_solver.log"),
    )
    print(f"Stage 2: {stage2_summary.status_name}")
    if stage2_summary.solution_count == 0:
        raise RuntimeError("Stage 2 did not produce a feasible incumbent")

    schedule = decode_schedule_solution(tasks, data.latency, schedule_model)
    validation = validate_schedule(
        schedule,
        tasks,
        data.gpu_info,
        data.latency,
        data.power_map,
        data.region_time,
    )

    schedule.to_csv(
        SCHEDULE_OUTPUT_DIR / "stage2_solution.csv",
        index=False,
        encoding="utf-8-sig",
    )
    schedule.to_csv(
        SCHEDULE_OUTPUT_DIR / "task_schedule.csv",
        index=False,
        encoding="utf-8-sig",
    )
    validation.resources.to_csv(
        SCHEDULE_OUTPUT_DIR / "region_hour_resource.csv",
        index=False,
        encoding="utf-8-sig",
    )
    write_json(
        SCHEDULE_OUTPUT_DIR / "stage2_summary.json",
        {
            **stage2_summary.as_dict(),
            "delta": args.delta,
            "peak_hour_scope": args.peak_hours,
            "stage1_objective_limit": (1 + args.delta)
            * stage1_summary.objective,
        },
    )

    validation_lines = [
        f"{name}: {value}" for name, value in validation.summary.items()
    ]
    (METRICS_OUTPUT_DIR / "validation_report.txt").write_text(
        "\n".join(validation_lines) + "\n", encoding="utf-8"
    )
    print("Validation:", "PASS" if validation.is_valid else "FAIL")
    if not validation.is_valid:
        validation.violations.to_csv(
            METRICS_OUTPUT_DIR / "validation_violations.csv",
            index=False,
            encoding="utf-8-sig",
        )
        raise RuntimeError("The decoded schedule failed independent validation")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
