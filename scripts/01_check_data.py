"""Load and validate the six raw data tables."""

from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.data_loader import load_raw_data  # noqa: E402
from src.config import METRICS_OUTPUT_DIR  # noqa: E402
from src.data_validator import (  # noqa: E402
    get_baseline_gpu_overloads,
    validate_data,
)


def write_audit_outputs(data, report) -> None:
    """Write validation results while keeping all source rows unchanged."""

    METRICS_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    lines = [
        "Raw Data Validation Report",
        f"Status: {'PASS' if report.is_valid else 'FAIL'}",
        f"ErrorCount: {len(report.errors)}",
        f"WarningCount: {len(report.warnings)}",
        "",
        "Tables:",
    ]
    lines.extend(
        f"- {name}: rows={len(table)}, columns={len(table.columns)}"
        for name, table in data.as_dict().items()
    )
    lines.extend(["", "Errors:"])
    lines.extend(f"- {message}" for message in report.errors)
    if not report.errors:
        lines.append("- None")
    lines.extend(["", "Warnings:"])
    lines.extend(f"- {message}" for message in report.warnings)
    if not report.warnings:
        lines.append("- None")

    report_path = METRICS_OUTPUT_DIR / "raw_data_validation_report.txt"
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8-sig")

    overloads = get_baseline_gpu_overloads(data.region_time)
    warning_path = METRICS_OUTPUT_DIR / "baseline_gpu_overload_warnings.csv"
    overloads.to_csv(warning_path, index=False, encoding="utf-8-sig")
    print(f"Saved validation report to {report_path}")
    print(f"Saved {len(overloads)} warning rows to {warning_path}")


def main() -> int:
    data = load_raw_data()
    print("Loaded tables:")
    for name, table in data.as_dict().items():
        print(f"  {name:<12} rows={len(table):>5}, columns={len(table.columns):>2}")

    report = validate_data(data)
    write_audit_outputs(data, report)
    for warning in report.warnings:
        print(f"WARNING: {warning}")

    if report.errors:
        for error in report.errors:
            print(f"ERROR: {error}")
        return 1

    print("Data validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
