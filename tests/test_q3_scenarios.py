"""合法历史数量、同日配对、不复制样本与场景非负化测试。"""

from datetime import date, timedelta
import unittest

import numpy as np

from src.q3.scenarios import W_S, build_scenarios


class ScenarioTests(unittest.TestCase):
    def test_two_available_dates_and_pairing(self):
        residuals = {date(2025, 1, 30)+timedelta(days=i):
                     {"load": np.array([i, i+1]), "pv": {0: np.array([-i, -i-1])}} for i in range(2)}
        result = build_scenarios(date(2025, 2, 1), 0, [10, 10], [10, 10], residuals)
        self.assertEqual(len(result["dates"]), 2)
        np.testing.assert_array_equal(result["load"]+result["pv"], np.full((2, 2), 20.))
        np.testing.assert_array_equal(result["probability"], [.5, .5])
        with self.assertRaisesRegex(ValueError, "未来"):
            build_scenarios(date(2025, 1, 31), 0, [10, 10], [10, 10], residuals)

    def test_window_fourteen_and_nonnegative_scenario_only(self):
        residuals = {date(2025, 1, 1)+timedelta(days=i):
                     {"load": np.array([-20.]), "pv": {0: np.array([float(i)])}} for i in range(20)}
        result = build_scenarios(date(2025, 2, 1), 0, [10.], [0.], residuals)
        self.assertEqual(W_S, 14)
        self.assertEqual(len(set(result["dates"])), 14)
        self.assertEqual(result["dates"][0], date(2025, 1, 7))
        np.testing.assert_allclose(result["probability"], np.full(14, 1/14))
        np.testing.assert_array_equal(result["load"], np.zeros((14, 1)))
        self.assertEqual(next(iter(residuals.values()))["load"][0], -20.)
