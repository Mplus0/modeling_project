"""实验层隔离、直接替换历史自洽、严格历史及冻结结果回归。"""

from datetime import date
from pathlib import Path
import json
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

from src.analysis.ablation_adapters import (zero_risk, q2_runner, DirectCache, direct_update,
                                           direct_history, direct_replay, run_q3_direct)
from src.analysis.model_validation import comparison_table, frozen_hashes, q2_validation, q3_validation
from src.q2.forecasting import load_daily_inputs
from src.q3.forecast import load_hourly_forecasts, update_pv
from src.q3.annual import HistoricalCache

ROOT = Path(__file__).resolve().parents[1]


class ModelValidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.before = frozen_hashes(ROOT)
        cls.history, cls.price = load_daily_inputs(ROOT / "data/processed/historical_power.csv", ROOT / "data/processed/q1_input.csv")
        cls.issues = load_hourly_forecasts(ROOT / "data/processed/pv_forecast_hourly.csv")
        cls.day = date(2025, 2, 1)
        cls.cache = DirectCache(cls.history, cls.issues)
        cls.load, cls.records, cls.residuals = cls.cache.prepare(cls.day)

    @classmethod
    def tearDownClass(cls):
        if cls.before != frozen_hashes(ROOT):
            raise AssertionError("冻结数据、正式Q2/Q3结果或源码发生变化")

    def test_zero_risk_does_not_consume_quantile_result(self):
        history = {date(2025, 1, 30): np.arange(144.), date(2025, 1, 31): -np.arange(144.)}
        before = {d: a.copy() for d, a in history.items()}
        with patch("src.q2.risk.empirical_quantile_type1", side_effect=AssertionError("不得计算风险分位数")):
            zero, dates = zero_risk(history, self.day)
        np.testing.assert_array_equal(zero, np.zeros(144))
        self.assertEqual(dates, sorted(history))
        for d in history:
            np.testing.assert_array_equal(history[d], before[d])
        with self.assertRaisesRegex(ValueError, "未来"):
            zero_risk({self.day: np.zeros(144)}, self.day)

    def test_q2_keeps_forecast_and_solver_dependencies(self):
        from src.q2.forecasting import forecast_day
        from src.q2.optimizer import solve_plan
        from src.q2.rolling import solve_actual_rolling_day
        runner = q2_runner(ROOT)
        for name, function in (("forecast_day", forecast_day), ("solve_plan", solve_plan),
                               ("solve_actual_rolling_day", solve_actual_rolling_day)):
            self.assertIs(runner.__globals__[name], function)
        self.assertIs(runner.__globals__["historical_risk"], zero_risk)
        self.assertNotIn("outputs/q2", runner.__code__.co_consts)
        self.assertIn("outputs/model_validation/q2_risk_ablation/run", runner.__code__.co_consts)

    def test_direct_remaining_and_executed_prefix(self):
        old = None
        for hour in (0, 6, 12, 18):
            anchor = 0.
            previous = None if old is None else old.copy()
            current, raw, conf = direct_update(self.day, hour, anchor, old, self.issues, self.records)
            np.testing.assert_array_equal(current[hour*6:], raw)
            if hour:
                np.testing.assert_array_equal(current[:hour*6], previous[:hour*6])
                np.testing.assert_array_equal(old, previous)
                self.assertEqual(conf["confidence_rho"], 1.)
            else:
                expected, _, _ = update_pv(self.day, hour, anchor, old, self.issues, self.records)
                np.testing.assert_array_equal(current, expected)
            old = current

    def test_history_uses_own_direct_versions_and_residuals(self):
        for day, record in self.cache.records.items():
            for hour in (6, 12, 18):
                np.testing.assert_array_equal(record["versions"][hour][hour*6:], record["updates"][hour]["new"][hour*6:])
                np.testing.assert_array_equal(record["versions"][hour][:hour*6], record["updates"][hour]["old"][:hour*6])
            if day in self.cache.residuals:
                for hour in (0, 6, 12, 18):
                    np.testing.assert_array_equal(self.cache.residuals[day]["pv"][hour], self.history[day]["pv"]-record["versions"][hour])
        original = HistoricalCache(self.history, self.issues)
        load, _, residuals = original.prepare(self.day)
        np.testing.assert_array_equal(self.load, load)
        self.assertEqual(sorted(self.residuals), sorted(residuals))
        for day in residuals:
            np.testing.assert_array_equal(self.residuals[day]["load"], residuals[day]["load"])
        self.assertTrue(any(not np.array_equal(self.residuals[d]["pv"][h], residuals[d]["pv"][h])
                            for d in residuals for h in (6, 12, 18)))

    def test_past_only_and_future_actual_invariance(self):
        self.assertTrue(all(d < self.day for d in self.records))
        self.assertTrue(all(d < self.day for d in self.residuals))
        with self.assertRaisesRegex(ValueError, "目标日"):
            direct_history({self.day: self.history[self.day]}, self.day, self.issues)
        with self.assertRaisesRegex(ValueError, "未来"):
            direct_update(self.day, 6, 0., np.zeros(144), self.issues, {self.day: {}})
        changed = {d: ({k: np.array(v, copy=True) for k, v in value.items()} if d >= self.day else value)
                   for d, value in self.history.items()}
        for d, value in changed.items():
            if d >= self.day:
                value["load"][:] = 99999
                value["pv"][:] = 88888
        load, records, residuals = DirectCache(changed, self.issues).prepare(self.day)
        np.testing.assert_array_equal(load, self.load)
        for d in residuals:
            for h in (0, 6, 12, 18):
                np.testing.assert_array_equal(residuals[d]["pv"][h], self.residuals[d]["pv"][h])

    def test_injection_reaches_target_and_history_without_global_patch(self):
        from src.q3 import simulation, forecast
        self.assertIs(run_q3_direct.__globals__["simulate_day"].__globals__["update_pv"], direct_update)
        self.assertIs(DirectCache.prepare.__globals__["replay_completed_day"], direct_replay)
        self.assertIs(simulation.simulate_day.__globals__["update_pv"], forecast.update_pv)
        self.assertIs(HistoricalCache.prepare.__globals__["replay_completed_day"], forecast.replay_completed_day)

    def test_relative_change_zero_and_sign(self):
        table = comparison_table({"zero": 1e-10, "cost": 100.}, {"zero": 2., "cost": 90.}, "A", "B")
        self.assertTrue(pd.isna(table.relative_change_percent.iloc[0]))
        self.assertAlmostEqual(table.difference.iloc[0], 2.-1e-10)
        self.assertEqual(table.relative_change_percent.iloc[1], -10.)

    def test_saved_comparison_matches_trajectories(self):
        from src.analysis.model_validation import common_metrics, read_csv
        base = ROOT / "outputs/model_validation/q3_confidence_ablation"
        if not (base / "q3_confidence_ablation_metrics.csv").exists():
            self.skipTest("Q3-C全年比较尚未生成")
        table = read_csv(base / "q3_confidence_ablation_metrics.csv").set_index("metric")
        for label, folder in (("Q3-C", base / "run"), ("Q3-D", ROOT / "outputs/q3/final")):
            outputs = {k: read_csv(folder / f"q3_{k}.csv") for k in ("actual_schedule", "daily_metrics")}
            for name, value in common_metrics(outputs).items():
                self.assertAlmostEqual(table.loc[name, label], value, delta=1e-6)
        np.testing.assert_allclose(table.difference, table["Q3-D"]-table["Q3-C"], atol=1e-6, rtol=0)
        self.assertTrue((base / "q3_confidence_ablation_by_update.csv").is_file())
        self.assertTrue((base / "q3_confidence_ablation_paper_summary.md").is_file())

    def test_saved_experiments_and_integrity_when_present(self):
        for kind, stem in (("q2", "q2_risk_ablation"), ("q3", "q3_confidence_ablation")):
            for name in ("smoke", "run"):
                directory = ROOT / "outputs/model_validation" / stem / name
                marker = directory / "attempt.json"
                if not marker.exists() or json.loads(marker.read_text(encoding="utf-8"))["status"] != "validated":
                    continue
                integrity = json.loads((directory / "integrity.json").read_text(encoding="utf-8"))
                self.assertTrue(integrity["unchanged"])
                self.assertEqual(integrity["before"], frozen_hashes(ROOT))
                if kind == "q2":
                    q2_validation(directory, ROOT / "outputs/q2", formal=name == "run")
                else:
                    from src.analysis.model_validation import DETAILS, read_csv
                    outputs = {k: read_csv(directory / f"q3_{k}.csv") for k in DETAILS}
                    q3_validation(outputs, formal=name == "run")


if __name__ == "__main__":
    unittest.main()
