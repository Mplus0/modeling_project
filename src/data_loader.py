"""Read the six source workbooks used by the competition problem.

This module deliberately performs no cleaning or model-specific filtering.
Validation belongs in ``data_validator.py`` so that malformed source data is
reported rather than silently repaired during loading.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from .config import RAW_DATA_DIR, RAW_DATA_FILES, RAW_DATA_SHEETS


@dataclass(frozen=True, slots=True)
class RawDataBundle:
    """The canonical data tables read from the six source workbooks."""

    tasks: pd.DataFrame
    gpu_info: pd.DataFrame
    latency: pd.DataFrame
    power_map: pd.DataFrame
    region_time: pd.DataFrame
    storage: pd.DataFrame

    def as_dict(self) -> dict[str, pd.DataFrame]:
        """Return the tables keyed by their canonical logical names."""

        return {
            "tasks": self.tasks,
            "gpu_info": self.gpu_info,
            "latency": self.latency,
            "power_map": self.power_map,
            "region_time": self.region_time,
            "storage": self.storage,
        }


def _resolve_data_dir(data_dir: str | Path | None) -> Path:
    """Resolve and validate the directory containing the raw workbooks."""

    resolved = RAW_DATA_DIR if data_dir is None else Path(data_dir)
    resolved = resolved.expanduser().resolve()
    if not resolved.is_dir():
        raise FileNotFoundError(f"Raw data directory does not exist: {resolved}")
    return resolved


def _read_table(data_dir: Path, logical_name: str) -> pd.DataFrame:
    """Read one configured worksheet and add context to read failures."""

    filename = RAW_DATA_FILES[logical_name]
    sheet_name = RAW_DATA_SHEETS[logical_name]
    workbook_path = data_dir / filename

    if not workbook_path.is_file():
        raise FileNotFoundError(
            f"Missing source workbook for '{logical_name}': {workbook_path}"
        )

    try:
        return pd.read_excel(
            workbook_path,
            sheet_name=sheet_name,
            engine="openpyxl",
        )
    except ValueError as exc:
        raise ValueError(
            f"Cannot read sheet '{sheet_name}' from {workbook_path.name}: {exc}"
        ) from exc
    except OSError as exc:
        raise OSError(f"Cannot read source workbook {workbook_path}: {exc}") from exc


def load_raw_data(data_dir: str | Path | None = None) -> RawDataBundle:
    """Load the canonical worksheet from every source workbook.

    Parameters
    ----------
    data_dir:
        Optional override for the directory containing the six workbooks.
        When omitted, ``<project>/data/raw`` is used.

    Returns
    -------
    RawDataBundle
        Unmodified pandas DataFrames. Descriptive sheets such as ``字段说明``
        are intentionally not loaded into the modeling data bundle.
    """

    resolved_dir = _resolve_data_dir(data_dir)
    tables = {
        logical_name: _read_table(resolved_dir, logical_name)
        for logical_name in RAW_DATA_FILES
    }
    return RawDataBundle(**tables)

