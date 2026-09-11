"""一级真实快照、诊断指标及正式结果冻结验证。"""

import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

import numpy as np
import pandas as pd

from src.common.data_loader import file_hash
from src.q1.comparison import write_comparison
from src.q1.optimizer import VALIDATION_TOL, load_input, solve_q1

ROOT = Path(__file__).resolve().parents[1]


class Q1ComparisonTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.frame = load_input(ROOT / "data/processed/q1_input.csv")
        cls.secondary, cls.metrics, cls.primary = solve_q1(cls.frame, capture_primary=True)

    def test_generated_outputs_and_objectives(self):
        with TemporaryDirectory() as directory:
            report = write_comparison(self.primary, self.secondary, self.metrics, directory)
            for name in ("q1_primary_only_schedule.csv", "q1_secondary_comparison.json", "q1_secondary_comparison.md"):
                self.assertTrue((Path(directory) / name).is_file())
            self.assertEqual(json.loads((Path(directory) / "q1_secondary_comparison.json").read_text(encoding="utf-8")), report)
            pd.testing.assert_frame_equal(pd.read_csv(Path(directory) / "q1_primary_only_schedule.csv",
                                                      float_precision="round_trip"), self.primary)
            self.assertEqual(len(report["core_indicators"]), 8)
            self.assertEqual(report["primary_status"], "optimal")
            self.assertEqual(report["secondary_status"], "optimal")
            self.assertIn("one optimal solution returned by SCIP", report["primary_solution_provenance"])
            h = []
            for label, schedule in (("一级原始解", self.primary), ("二级优化后", self.secondary)):
                cost = float(sum(schedule.price_yuan_per_kwh * (schedule.x_kwh + schedule.y_kwh)))
                throughput = float(sum(0.9 * (schedule.x_kwh + schedule.q_kwh) + schedule.z_kwh / 0.9))
                h.append(throughput)
                self.assertAlmostEqual(cost, self.metrics["C_star"], delta=VALIDATION_TOL)
                self.assertAlmostEqual(report["core_indicators"][label + "全天购电费用"], cost, delta=VALIDATION_TOL)
                self.assertAlmostEqual(report["core_indicators"][label + "储能总吞吐量 H"], throughput, delta=VALIDATION_TOL)
                count = int(((schedule.x_kwh + schedule.q_kwh > VALIDATION_TOL) & (schedule.z_kwh > VALIDATION_TOL)).sum())
                self.assertEqual(report["core_indicators"][label + "同时充放电有效时段数"], count)
            self.assertLessEqual(h[1], h[0] + VALIDATION_TOL)
            self.assertAlmostEqual(report["core_indicators"]["储能总吞吐量下降量"], h[0] - h[1], delta=VALIDATION_TOL)
            self.assertAlmostEqual(report["core_indicators"]["储能总吞吐量下降比例"], (h[0] - h[1]) / h[0] * 100, delta=VALIDATION_TOL)

    def test_both_schedules_original_constraints(self):
        # 测试从变量直接复算，避免仅信任报告中的通过标记。
        for s in (self.primary, self.secondary):
            with self.subTest(stage="primary" if s is self.primary else "secondary"):
                self.assertEqual(len(s), 144)
                self.assertFalse(s.isna().any().any())
                self.assertGreaterEqual(s[["x_kwh", "y_kwh", "q_kwh", "z_kwh"]].to_numpy().min(), -VALIDATION_TOL)
                self.assertGreaterEqual(s.soc_kwh.min(), 1200 - VALIDATION_TOL)
                self.assertLessEqual(s.soc_kwh.max(), 10800 + VALIDATION_TOL)
                self.assertAlmostEqual(s.soc_previous_kwh.iloc[0], 6000, delta=VALIDATION_TOL)
                self.assertAlmostEqual(s.soc_kwh.iloc[-1], 6000, delta=VALIDATION_TOL)
                np.testing.assert_allclose(s.soc_kwh, np.r_[6000, s.soc_kwh.to_numpy()[:-1]] +
                                           0.9 * (s.x_kwh + s.q_kwh) - s.z_kwh / 0.9, rtol=0, atol=VALIDATION_TOL)
                self.assertTrue((s.q_kwh <= s.pv_forecast_kwh + VALIDATION_TOL).all())
                self.assertTrue((s.x_kwh + s.q_kwh <= 5000 / 6 + VALIDATION_TOL).all())
                self.assertTrue((s.z_kwh <= 5000 / 6 + VALIDATION_TOL).all())
                self.assertTrue((s.pv_forecast_kwh - s.q_kwh + s.y_kwh + s.z_kwh >= s.load_kwh - VALIDATION_TOL).all())

    def test_zero_throughput_percentage(self):
        frame = self.frame.copy()
        frame[["load_kw", "load_kwh", "pv_forecast_kw", "pv_forecast_kwh"]] = 0.0
        secondary, metrics, primary = solve_q1(frame, capture_primary=True)
        with TemporaryDirectory() as directory:
            report = write_comparison(primary, secondary, metrics, directory)
            self.assertEqual(report["core_indicators"]["储能总吞吐量下降比例"], 0.0)

    def test_invalid_schedule_rejected(self):
        invalid = self.primary.copy()
        invalid.loc[0, "soc_kwh"] += 10
        with TemporaryDirectory() as directory, self.assertRaisesRegex(ValueError, "独立约束"):
            write_comparison(invalid, self.secondary, self.metrics, directory)

    def test_entrypoint_preserves_official_results(self):
        # 直接运行用户入口，逐字节核对正式结果及论文表未被写回。
        protected = [ROOT / p for p in ("outputs/schedule/q1_schedule.csv", "outputs/metrics/q1_metrics.json",
                                        "outputs/submissions/result1.xlsx")]
        protected += sorted((ROOT / "outputs").rglob("*paper*"))
        before = {p: file_hash(p) for p in protected if p.is_file()}
        result = subprocess.run([sys.executable, "-X", "utf8", "scripts/03_run_q1.py"], cwd=ROOT,
                                capture_output=True, text=True, encoding="utf-8", timeout=120)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(before, {p: file_hash(p) for p in before})
        for name in ("q1_primary_only_schedule.csv", "q1_secondary_comparison.json", "q1_secondary_comparison.md"):
            self.assertTrue((ROOT / "outputs/comparison" / name).is_file())


if __name__ == "__main__":
    unittest.main()
