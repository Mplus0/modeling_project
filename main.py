"""Reproduce all implemented outputs for Question 1."""

from argparse import ArgumentParser
from pathlib import Path
import subprocess
import sys

from src.config import (
    PEAK_HOUR_SCOPE,
    SERVICE_DEGRADATION_DELTA,
    SOLVER_MIP_GAP,
    SOLVER_TIME_LIMIT,
    WAIT_NORMALIZATION_EPSILON,
)


PROJECT_ROOT = Path(__file__).resolve().parent


def main() -> int:
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--question", type=int, choices=(1,), default=1)
    parser.add_argument(
        "--epsilon", type=float, default=WAIT_NORMALIZATION_EPSILON
    )
    parser.add_argument(
        "--delta", type=float, default=SERVICE_DEGRADATION_DELTA
    )
    parser.add_argument(
        "--peak-hours",
        choices=("evaluation", "resource"),
        default=PEAK_HOUR_SCOPE,
    )
    parser.add_argument("--time-limit", type=float, default=SOLVER_TIME_LIMIT)
    parser.add_argument("--mip-gap", type=float, default=SOLVER_MIP_GAP)
    args = parser.parse_args()

    scripts = [
        ["scripts/01_check_data.py"],
        ["scripts/02_build_demand.py"],
        ["scripts/03_run_forecast.py"],
        [
            "scripts/04_run_schedule.py",
            "--epsilon",
            str(args.epsilon),
            "--delta",
            str(args.delta),
            "--peak-hours",
            args.peak_hours,
        ],
        ["scripts/05_generate_report_outputs.py"],
    ]
    if args.time_limit is not None:
        scripts[3].extend(["--time-limit", str(args.time_limit)])
    if args.mip_gap is not None:
        scripts[3].extend(["--mip-gap", str(args.mip_gap)])

    for command in scripts:
        subprocess.run(
            [sys.executable, *command], cwd=PROJECT_ROOT, check=True
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
