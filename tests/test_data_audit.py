"""用合成数据验证审计边界，不改动任何官方附件。"""

from datetime import datetime, time
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import pandas as pd
from openpyxl import Workbook

from src.common.data_loader import file_hash, load_sheets
from src.common.data_validator import validate_sheet
from src.common.time_utils import audit_axis, clock_seconds, inspect_times


class AuditTests(unittest.TestCase):
    def test_explicit_rollover_and_gaps(self):
        self.assertEqual(clock_seconds("0:00+1"), 86400)
        self.assertEqual(clock_seconds("24:00"), 86400)
        self.assertIsNone(clock_seconds("24:10"))
        result = audit_axis([600, 1800, 1800, 1200, 3000, None], 600)
        self.assertEqual(result["missing_timestamps"], [2400])
        self.assertEqual(result["duplicate_extra_count"], 1)
        self.assertEqual(result["non_increasing_intervals"], 2)
        self.assertEqual(result["unresolved_records"], 1)

    def test_forecast_never_fills_dates(self):
        frame = pd.DataFrame([["2025-1-1", "0:00", 1], ["", "6:00", 2]], dtype=object)
        original = frame.copy(deep=True)
        result = inspect_times(frame, ["日期", "预报时刻", "预报1小时"])
        self.assertEqual(result["forecast"]["unresolved_issue_excel_rows"], [3])
        self.assertEqual(result["forecast"]["targets_by_explicit_issue"][0]["target_times"], ["2025-01-01T01:00:00"])
        pd.testing.assert_frame_equal(frame, original)

    def test_wide_table_daily_boundary(self):
        frame = pd.DataFrame([[datetime(2025, 1, 1), 0, None]], dtype=object)
        result = inspect_times(frame, ["日期\\时间", time(23, 50), "0:00+1"])
        axis = result["axes"]["date_and_header_times"]
        self.assertEqual(axis["records_per_calendar_day"], {"2025-01-01": 1, "2025-01-02": 1})
        self.assertEqual(result["records_per_source_day"][0]["nonblank_values"], 1)
        self.assertEqual(axis["missing_timestamp_count"], 0)

    def test_raw_cells_headers_formulas_and_hash(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "sample.xlsx"
            workbook = Workbook()
            sheet = workbook.active
            sheet.append(["值", "值", None])
            sheet.append([-1, "NA", "=1+1"])
            sheet.append([0, "3", None])
            sheet.append([0, "3", None])
            workbook.save(path)
            workbook.close()
            before = file_hash(path)
            loaded = list(load_sheets(path))[0]
            original = loaded["frame"].copy(deep=True)
            result = validate_sheet(loaded)
            self.assertEqual(result["duplicate_header_names"], ["值"])
            self.assertEqual(result["duplicated_rows_extra"], 1)
            self.assertEqual(result["columns"][0]["negative_count"], 1)
            self.assertEqual(result["columns"][0]["zero_count"], 2)
            self.assertEqual(result["columns"][1]["numeric_count"], 0)
            self.assertEqual(result["columns"][1]["missing_count"], 0)
            self.assertEqual(result["columns"][2]["formula_count"], 1)
            self.assertEqual(result["columns"][2]["missing_count"], 2)
            pd.testing.assert_frame_equal(loaded["frame"], original)
            self.assertEqual(file_hash(path), before)


if __name__ == "__main__":
    unittest.main()
