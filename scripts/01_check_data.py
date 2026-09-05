"""Load and validate the six raw data tables."""

from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.data_loader import load_raw_data  # noqa: E402
from src.data_validator import validate_data  # noqa: E402


def main() -> int:
    data = load_raw_data()
    print("Loaded tables:")
    for name, table in data.as_dict().items():
        print(f"  {name:<12} rows={len(table):>5}, columns={len(table.columns):>2}")

    report = validate_data(data)
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

