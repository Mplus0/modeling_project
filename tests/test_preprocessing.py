"""官方附件集成验证和错误结构拒绝测试；输出仅写入临时目录。"""

from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import numpy as np
import pandas as pd

from src.common.data_loader import discover_workbooks, file_hash, load_sheets
from src.common.preprocessing import preprocess_forecast, preprocess_q1, preprocess_wide, run_preprocessing

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data/raw"


class PreprocessingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = TemporaryDirectory()
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.directory = Path(cls.temporary.name)
        cls.hashes = {p: file_hash(p) for p in discover_workbooks(RAW)}
        cls.outputs, cls.filled_rows = run_preprocessing(
            RAW, cls.directory / "processed", cls.directory / "preprocessing_summary.md")
        cls.books = {n: list(load_sheets(RAW / f"附件{n}.xlsx")) for n in range(1, 5)}

    def test_row_counts_and_no_missing_values(self):
        counts = {"q1_input.csv": 144, "historical_power.csv": 52560,
                  "pv_forecast_hourly.csv": 35040, "electricity_price.csv": 52560}
        for name, expected in counts.items():
            with self.subTest(file=name):
                frame = self.outputs[name]
                self.assertEqual(len(frame), expected)
                self.assertFalse(frame.isna().any().any())
                saved = pd.read_csv(self.directory / "processed" / name, float_precision="round_trip")
                self.assertEqual(list(saved.columns), list(frame.columns))
                self.assertEqual(len(saved), expected)
                self.assertFalse(saved.isna().any().any())
                for column in frame.columns:
                    if column.endswith(("_kw", "_kwh")):
                        np.testing.assert_array_equal(saved[column].to_numpy(), frame[column].to_numpy())

    def test_datetime_uniqueness_and_rollover(self):
        for name in ("historical_power.csv", "electricity_price.csv"):
            frame = self.outputs[name]
            self.assertTrue(frame["datetime"].is_unique)
            self.assertTrue(frame["datetime"].diff().iloc[1:].eq(pd.Timedelta(minutes=10)).all())
            self.assertEqual(frame.iloc[143]["source_time"], "0:00+1")
            self.assertEqual(frame.iloc[143]["source_date"], "2025-01-01")
            self.assertEqual(frame.iloc[143]["datetime"], pd.Timestamp("2025-01-02 00:00"))
            self.assertEqual(frame.iloc[-1]["datetime"], pd.Timestamp("2026-01-01 00:00"))

    def test_energy_conversion_and_original_values(self):
        q1 = self.outputs["q1_input.csv"]
        self.assertEqual(q1["slot"].tolist(), list(range(1, 145)))
        self.assertEqual(q1["source_time"].tolist(), self.books[1][0]["frame"].iloc[:, 0].map(str).tolist())
        for source, target in ((1, "price_yuan_per_kwh"), (2, "load_kw"), (3, "pv_forecast_kw")):
            np.testing.assert_array_equal(q1[target], self.books[1][0]["frame"].iloc[:, source])
        historical = self.outputs["historical_power.csv"]
        sheets = {s["sheet"]: s for s in self.books[2]}
        for sheet_name, target in (("小区负载", "load_kw"), ("光伏发电实际功率", "pv_actual_kw")):
            np.testing.assert_array_equal(historical[target], sheets[sheet_name]["frame"].iloc[:, 1:].to_numpy().ravel())
        price = self.outputs["electricity_price.csv"]
        np.testing.assert_array_equal(price["price_yuan_per_kwh"], self.books[4][0]["frame"].iloc[:, 1:].to_numpy().ravel())
        for frame, pairs in ((q1, [("load_kw", "load_kwh"), ("pv_forecast_kw", "pv_forecast_kwh")]),
                             (historical, [("load_kw", "load_kwh"), ("pv_actual_kw", "pv_actual_kwh")])):
            for power, energy in pairs:
                np.testing.assert_allclose(frame[energy].to_numpy(dtype=float), frame[power].to_numpy(dtype=float) / 6,
                                           rtol=1e-14, atol=1e-12)

    def test_issue_structure_and_targets(self):
        forecast = self.outputs["pv_forecast_hourly.csv"]
        issues = forecast["issue_datetime"].drop_duplicates()
        self.assertEqual(len(issues), 1460)
        self.assertEqual(set(issues.dt.hour), {0, 6, 12, 18})
        self.assertTrue(issues.groupby(issues.dt.date).size().eq(4).all())
        self.assertTrue(forecast.groupby("issue_datetime").size().eq(24).all())
        self.assertFalse(forecast.duplicated(["issue_datetime", "target_datetime"]).any())
        self.assertEqual(forecast["horizon_hour"].tolist(), list(range(1, 25)) * 1460)
        self.assertTrue((forecast["target_datetime"] - forecast["issue_datetime"] ==
                         pd.to_timedelta(forecast["horizon_hour"], unit="h")).all())
        np.testing.assert_array_equal(forecast["pv_forecast_kw"], self.books[3][0]["frame"].iloc[:, 2:].to_numpy().ravel())
        self.assertEqual(len(self.filled_rows), 1095)
        original = self.books[3][0]["frame"].copy(deep=True)
        preprocess_forecast(self.books[3][0])
        pd.testing.assert_frame_equal(original, self.books[3][0]["frame"])

    def test_invalid_issue_groups_stop(self):
        # 保持总行数不变，分别注入缺失组首、重复时刻、乱序和跨组日期错误。
        mutations = [(0, 0, ""), (1, 1, "0:00"), (1, 1, "12:00"),
                     (1, 0, "2025-1-2"), (4, 0, "2025-1-1"), (4, 0, "invalid")]
        for row, column, value in mutations:
            with self.subTest(row=row, column=column, value=value):
                sheet = deepcopy(self.books[3][0])
                sheet["frame"].iat[row, column] = value
                with self.assertRaisesRegex(ValueError, "附件 3"):
                    preprocess_forecast(sheet)
        sheet = deepcopy(self.books[3][0])
        sheet["frame"] = sheet["frame"].iloc[:-1]
        with self.assertRaisesRegex(ValueError, "尺寸"):
            preprocess_forecast(sheet)

    def test_unexpected_missing_and_bad_time_stop(self):
        for value in (None, "12", float("inf")):
            sheet = deepcopy(self.books[1][0])
            sheet["frame"].iat[0, 1] = value
            with self.assertRaises(ValueError):
                preprocess_q1(sheet)
        sheet = deepcopy(self.books[4][0])
        sheet["headers"][-1] = "0:00"
        with self.assertRaises(ValueError):
            preprocess_wide(sheet, "price_yuan_per_kwh")

    def test_raw_hashes_and_templates_unchanged(self):
        self.assertEqual(self.hashes, {p: file_hash(p) for p in discover_workbooks(RAW)})
        self.assertEqual(len(self.hashes), 9)
        self.assertEqual(len(list((self.directory / "processed").iterdir())), 4)
        report = (self.directory / "preprocessing_summary.md").read_text(encoding="utf-8")
        self.assertIn("SHA-256 完整性：通过", report)

    def test_reject_raw_output_directory(self):
        with self.assertRaisesRegex(ValueError, "输出路径"):
            run_preprocessing(RAW, RAW, self.directory / "unsafe.md")


if __name__ == "__main__":
    unittest.main()
