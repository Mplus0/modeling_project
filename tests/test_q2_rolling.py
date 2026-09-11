"""因果信息集、三级目标优先级、真实执行及固定日初参考的合成验证。"""

import inspect
import unittest
from unittest.mock import patch

import numpy as np

from src.q2.rolling import (COST_LOCK_TOLERANCE, TERMINAL_GAP_LOCK_TOLERANCE,
                            solve_actual_rolling_step, solve_actual_rolling_day)


class RollingTests(unittest.TestCase):
    def step(self, load, pv, commitment, current=1200., day_start=1200., price=None):
        n = len(load)
        return solve_actual_rolling_step(1, load[0], pv[0], load, pv,
                                         np.ones(n) if price is None else price,
                                         commitment, current, day_start, "synthetic")

    def test_secondary_retains_soc_at_same_emergency_cost(self):
        # 不充电同为零紧急费但缺口90；二级应将富余100kWh充入电池以消除缺口。
        frame, m = self.step([0.], [100.], [0.], current=1200., day_start=1290.)
        self.assertAlmostEqual(m["primary_star"], 0., delta=1e-6)
        self.assertAlmostEqual(m["terminal_gap_star"], 0., delta=1e-6)
        self.assertAlmostEqual(frame.soc_real_end_kwh.iloc[-1], 1290., delta=1e-6)
        self.assertAlmostEqual(m["tertiary_objective"], 90., delta=1e-6)

    def test_primary_cost_precedes_soc_restoration(self):
        # 10kWh负荷耗去初始可用电，保留SOC需另付50元紧急费，故允许正缺口。
        frame, m = self.step([10.], [0.], [0.], current=1200+10/0.9,
                              day_start=1200+10/0.9)
        self.assertAlmostEqual(m["primary_star"], 0., delta=1e-6)
        self.assertAlmostEqual(m["terminal_gap_star"], 10/0.9, delta=1e-6)
        self.assertAlmostEqual(frame.soc_real_end_kwh.iloc[-1], 1200., delta=1e-6)

    def test_tertiary_avoids_unnecessary_throughput(self):
        # 零缺口下仍可额外充电；三级选择不充电，不对超出日初SOC施加上界。
        frame, m = self.step([0., 0.], [100., 100.], [0., 0.], current=6000., day_start=5000.)
        self.assertAlmostEqual(m["terminal_gap_star"], 0., delta=1e-6)
        self.assertAlmostEqual(m["tertiary_objective"], 0., delta=1e-6)
        self.assertAlmostEqual(frame.soc_real_end_kwh.iloc[-1], 6000., delta=1e-6)

    def test_fixed_day_start_reference_and_all_locks(self):
        frame, m = self.step([0.], [0.], [0.], current=4000., day_start=6000.)
        self.assertAlmostEqual(m["terminal_gap_star"], 2000., delta=1e-6)
        self.assertGreaterEqual(m["terminal_gap"], -1e-6)
        self.assertGreaterEqual(frame.soc_real_end_kwh.iloc[-1]+m["terminal_gap"], 6000.-1e-6)
        self.assertLessEqual(abs(m["cost"]-m["primary_star"]), COST_LOCK_TOLERANCE+1e-8)
        self.assertLessEqual(abs(m["terminal_gap"]-m["terminal_gap_star"]), TERMINAL_GAP_LOCK_TOLERANCE+1e-8)
        self.assertEqual([m[f"{stage}_status"] for stage in ("primary", "secondary", "tertiary")], ["optimal"]*3)

    def test_step_information_set_and_past_removed(self):
        names = inspect.signature(solve_actual_rolling_step).parameters
        self.assertEqual([k for k in names if "actual" in k], ["current_actual_load", "current_actual_pv"])
        frame, _ = solve_actual_rolling_step(2, 5., 3., [999., 99., 7.], [999., 99., 2.],
                                            [1., 1., 1.], [0., 0., 0.], 6000., 6000., "test")
        self.assertEqual(frame.slot.tolist(), [2, 3])
        np.testing.assert_array_equal(frame.load_actual_kwh, [5., 7.])
        np.testing.assert_array_equal(frame.pv_actual_kwh, [3., 2.])

    def test_future_actual_changes_cannot_change_current_decision(self):
        def run(future):
            seen = []
            forecast, pv = np.array([10., 10., 10.]), np.zeros(3)
            def observer(slot):
                seen.append(slot)
                return ([10., *future][slot-1], 0.)
            frame, _ = solve_actual_rolling_day(observer, forecast, pv, np.ones(3), np.zeros(3), 6000., "test")
            self.assertEqual(seen, [1, 2, 3])
            np.testing.assert_array_equal(forecast, [10., 10., 10.])
            np.testing.assert_array_equal(frame.load_forecast_kwh, forecast)
            return frame
        a, b = run([10., 10.]), run([100., 200.])
        for v in ("x_real_kwh", "y_real_kwh", "q_real_kwh", "z_real_kwh", "emergency_purchase_kwh", "soc_real_end_kwh"):
            self.assertEqual(a[v].iloc[0], b[v].iloc[0])

    def test_current_only_execution_and_real_soc_inheritance(self):
        original = solve_actual_rolling_step
        starts, day_starts = [], []
        def tracked(*args):
            starts.append(args[-3])
            day_starts.append(args[-2])
            frame, check = original(*args)
            # 污染未执行的未来SOC，下一轮不应使用它，执行结果也不能含未来行。
            if len(frame) > 1:
                frame.loc[1:, "soc_real_end_kwh"] = 9876.
            return frame, check
        with patch("src.q2.rolling.solve_actual_rolling_step", side_effect=tracked):
            actual, check = solve_actual_rolling_day(lambda t: (10., 0.), [10.]*3, [0.]*3,
                                                     [1.]*3, [0.]*3, 6000., "test")
        self.assertEqual(actual.slot.tolist(), [1, 2, 3])
        np.testing.assert_allclose(starts, actual.soc_real_start_kwh, atol=1e-6, rtol=0)
        np.testing.assert_allclose(starts[1:], actual.soc_real_end_kwh.iloc[:-1], atol=1e-6, rtol=0)
        self.assertEqual(day_starts, [6000.]*3)
        self.assertAlmostEqual(check["cost"], float((5*actual.price_yuan_per_kwh*actual.emergency_purchase_kwh).sum()), delta=1e-6)
        self.assertAlmostEqual(check["throughput"], float((0.9*(actual.x_real_kwh+actual.q_real_kwh)+actual.z_real_kwh/0.9).sum()), delta=1e-6)

    def test_forecast_is_frozen_before_first_observation(self):
        load, pv = np.array([10., 20., 30.]), np.array([1., 2., 3.])
        def observer(slot):
            # 外部观测过程改变原数组，也不得改变日初已冻结的未来预测。
            load[:] = 999.
            pv[:] = 888.
            return 10., 0.
        actual, _ = solve_actual_rolling_day(observer, load, pv, np.ones(3), np.zeros(3), 6000., "test")
        np.testing.assert_array_equal(actual.load_forecast_kwh, [10., 20., 30.])
        np.testing.assert_array_equal(actual.pv_forecast_kwh, [1., 2., 3.])

    def test_executed_totals_do_not_sum_overlapping_objectives(self):
        actual, check = solve_actual_rolling_day(lambda t: (10., 0.), [10.]*3, [0.]*3,
                                                 [1.]*3, [0.]*3, 1200., "test")
        self.assertAlmostEqual(check["cost"], 150., delta=1e-6)
        self.assertAlmostEqual(actual.rolling_primary_star_yuan.sum(), 300., delta=1e-6)
        actual, check = solve_actual_rolling_day(lambda t: (10., 0.), [10.]*3, [0.]*3,
                                                 [1.]*3, [0.]*3, 6000., "test")
        self.assertAlmostEqual(check["throughput"], 30/0.9, delta=1e-6)
        self.assertAlmostEqual(actual.rolling_tertiary_throughput_star_kwh.sum(), 60/0.9, delta=1e-6)
