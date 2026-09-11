"""先单日基准再全年运行的独立复核；冻结文件与历史存档的完整性检查。"""

import json
from pathlib import Path
import unittest

import numpy as np
import pandas as pd

from src.common.data_loader import file_hash
from src.q2.optimizer import validate_schedule, VALIDATION_TOL

ROOT = Path(__file__).resolve().parents[1]


class OneDayTests(unittest.TestCase):
    def test_benchmark_executed_constraints_and_totals(self):
        folder = ROOT / "outputs/comparison/q2_rolling_benchmark"
        actual = pd.read_csv(folder / "q2_actual_schedule.csv", float_precision="round_trip")
        plan = pd.read_csv(folder / "q2_plan_schedule.csv", float_precision="round_trip")
        metrics = json.loads((folder / "q2_metrics.json").read_text(encoding="utf-8"))
        self.assertEqual(actual.slot.tolist(), list(range(1, 145)))
        self.assertEqual(actual.date.unique().tolist(), ["2025-02-01"])
        self.assertEqual(metrics["total_actual_lp_optimizations"], 432)
        self.assertEqual(metrics["actual_operation_mode"], "rolling_horizon_causal")
        np.testing.assert_array_equal(actual.grid_purchase_plan_kwh, plan.grid_purchase_plan_kwh)
        np.testing.assert_array_equal(actual.rolling_horizon_length, np.arange(144, 0, -1))
        checked = validate_schedule(actual, "actual", 6000.)
        self.assertLessEqual(checked["max_violation"], VALIDATION_TOL)
        self.assertLessEqual(actual.rolling_max_constraint_violation.max(), VALIDATION_TOL)
        for stage in ("primary", "secondary", "tertiary"):
            self.assertTrue(actual[f"rolling_{stage}_status"].eq("optimal").all())
        self.assertAlmostEqual(checked["cost"], metrics["total_emergency_cost_yuan"], delta=VALIDATION_TOL)
        self.assertAlmostEqual(checked["throughput"], metrics["total_actual_executed_throughput_kwh"], delta=VALIDATION_TOL)
        np.testing.assert_allclose(actual.soc_day_start_kwh, 6000., rtol=0, atol=0)
        self.assertFalse(actual.isna().any().any())

    def test_integrity_and_expost_archive(self):
        folder = ROOT / "outputs/comparison/q2_rolling_benchmark"
        checks = json.loads((folder / "q2_integrity.json").read_text(encoding="utf-8"))
        for name, hashes in checks.items():
            self.assertEqual(hashes["before"], hashes["after"])
            self.assertEqual(file_hash(ROOT / name), hashes["before"])
        archive = ROOT / "outputs/comparison/archive/q2_expost"
        for name, checksum in json.loads((archive / "archive_sha256.json").read_text(encoding="utf-8")).items():
            self.assertEqual(file_hash(archive / name), checksum)

    def test_formal_entrypoint_is_causal(self):
        source = (ROOT / "scripts/05_run_q2.py").read_text(encoding="utf-8")
        self.assertIn("solve_actual_rolling_day(observe_current", source)
        self.assertNotIn("solve_actual_expost_legacy", source)
        self.assertNotIn("solve_actual(", source)


class FullYearRollingTests(unittest.TestCase):
    def test_metrics_and_comparison_recompute(self):
        output = ROOT / "outputs/q2"
        m = json.loads((output / "q2_metrics.json").read_text(encoding="utf-8"))
        actual = pd.read_csv(output / "q2_actual_schedule.csv", float_precision="round_trip")
        daily = pd.read_csv(output / "q2_daily_metrics.csv", float_precision="round_trip")
        self.assertEqual(m["actual_operation_mode"], "rolling_horizon_causal")
        self.assertEqual(m["total_rolling_steps"], 48096)
        self.assertEqual(m["total_actual_lp_optimizations"], 144288)
        for stage in ("primary", "secondary", "tertiary"):
            self.assertEqual(m[f"rolling_{stage}_status_counts"], {"optimal": 48096})
        self.assertEqual(m["cost_lock_tolerance_yuan"], 1e-7)
        self.assertEqual(m["terminal_gap_lock_tolerance_kwh"], 1e-7)
        self.assertAlmostEqual(m["total_emergency_cost_yuan"], float((5*actual.price_yuan_per_kwh*actual.emergency_purchase_kwh).sum()), delta=1e-6)
        self.assertAlmostEqual(m["total_actual_cost_yuan"], float((actual.planned_cost_slot_yuan+actual.emergency_cost_slot_yuan).sum()), delta=1e-6)
        self.assertAlmostEqual(m["total_actual_executed_throughput_kwh"], float((.9*(actual.x_real_kwh+actual.q_real_kwh)+actual.z_real_kwh/.9).sum()), delta=1e-6)
        np.testing.assert_allclose(daily.actual_end_soc_deficit_kwh,
                                   np.maximum(0, daily.soc_start_kwh-daily.soc_actual_end_kwh), atol=1e-6, rtol=0)
        for index, day in daily.iterrows():
            group = actual.iloc[index*144:(index+1)*144]
            np.testing.assert_allclose(group.soc_day_start_kwh, day.soc_start_kwh, rtol=0, atol=0)
            np.testing.assert_array_equal(group.rolling_horizon_length, np.arange(144, 0, -1))
            self.assertAlmostEqual(day.actual_end_soc_deficit_kwh, group.rolling_terminal_gap_star_kwh.iloc[-1], delta=1e-6)
        comparison = json.loads((ROOT / "outputs/comparison/q2_expost_vs_rolling.json").read_text(encoding="utf-8"))
        old = json.loads((ROOT / "outputs/comparison/archive/q2_expost/q2_metrics.json").read_text(encoding="utf-8"))
        row = comparison["comparison"]["total_emergency_purchase_kwh"]
        self.assertEqual(row["old"], old["total_emergency_purchase_kwh"])
        self.assertEqual(row["new"], m["total_emergency_purchase_kwh"])
        self.assertAlmostEqual(row["absolute_difference"], row["new"]-row["old"], delta=1e-6)
        self.assertTrue((ROOT / "outputs/comparison/q2_expost_vs_rolling.md").is_file())

    def test_forecasting_and_risk_outputs_unchanged(self):
        # 改动只影响实际调度与继承的SOC，预测和风险输出应与旧版逐字节相同。
        archive = ROOT / "outputs/comparison/archive/q2_expost"
        for name in ("q2_predictions.csv", "q2_window_selection.csv", "q2_warmup_predictions.csv", "q2_warmup_windows.csv"):
            self.assertEqual(file_hash(ROOT / "outputs/q2" / name), file_hash(archive / name))

    def test_full_run_frozen_files(self):
        checks = json.loads((ROOT / "outputs/q2/q2_integrity.json").read_text(encoding="utf-8"))
        for name, hashes in checks.items():
            self.assertEqual(hashes["before"], hashes["after"])
            self.assertEqual(file_hash(ROOT / name), hashes["before"])
