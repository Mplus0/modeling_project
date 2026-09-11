from datetime import date, timedelta
from pathlib import Path
import unittest
import numpy as np

from src.q2.forecasting import FORMAL_DATES, K_PV, M_LOAD, candidate_prediction, forecast_day, load_daily_inputs, nmae, select_window


class ForecastingTests(unittest.TestCase):
    def history(self):
        return {date(2025, 1, 1) + timedelta(days=i): {"load": np.full(144, 10.0), "pv": np.full(144, 2.0)} for i in range(31)}

    def test_formal_shape_and_candidates(self):
        root = Path(__file__).resolve().parents[1]
        days, price = load_daily_inputs(root / "data/processed/historical_power.csv", root / "data/processed/q1_input.csv")
        self.assertEqual(FORMAL_DATES[0], date(2025, 2, 1))
        self.assertEqual(len(FORMAL_DATES), 334)
        self.assertTrue(all(len(days[d]["load"]) == 144 for d in FORMAL_DATES))
        self.assertEqual(len(price), 144)
        self.assertEqual(M_LOAD, (1, 2, 3, 4))
        self.assertEqual(K_PV, (3, 5, 7, 14))

    def test_nmae_and_ties(self):
        self.assertAlmostEqual(nmae([2, 3], [1, 5]), 3 / 5)
        self.assertEqual(select_window({4: 0.1, 1: 0.1 + 1e-14}), 1)

    def test_common_dates_and_no_future(self):
        history = self.history()
        forecast, info = forecast_day(history, date(2025, 2, 1))
        self.assertEqual(info["load_backtest_days"], 3)
        self.assertEqual(info["pv_backtest_days"], 17)
        self.assertEqual(info["load_backtest_first"], "2025-01-29")
        self.assertEqual(info["load_window_weeks"], 1)
        self.assertEqual(info["pv_window_days"], 3)
        np.testing.assert_array_equal(forecast["load"], np.full(144, 10.0))
        history[date(2025, 2, 1)] = history[date(2025, 1, 1)]
        with self.assertRaisesRegex(ValueError, "未来"):
            forecast_day(history, date(2025, 2, 1))

    def test_warmup_and_candidate_past_only(self):
        history = self.history()
        first = date(2025, 1, 30)
        with self.assertRaisesRegex(ValueError, "公共回测"):
            forecast_day({d: v for d, v in history.items() if d < first - timedelta(days=1)}, first - timedelta(days=1))
        _, info = forecast_day({d: v for d, v in history.items() if d < first}, first)
        self.assertEqual(info["load_backtest_days"], 1)
        old = candidate_prediction(history, first, "load", 2)
        history[first] = {"load": np.full(144, 1e9), "pv": np.full(144, 1e9)}
        np.testing.assert_array_equal(old, candidate_prediction(history, first, "load", 2))

    def test_candidate_scores_use_identical_evaluation_dates(self):
        history = self.history()
        for i, day in enumerate(history):
            history[day] = {"load": np.full(144, 10 + i * i), "pv": np.full(144, 2 + i)}
        target = date(2025, 2, 1)
        _, info = forecast_day(history, target)
        for kind, windows, prefix in [("load", M_LOAD, "m"), ("pv", K_PV, "k")]:
            dates = [date.fromisoformat(d) for d in info[f"{kind}_backtest_dates"].split("|")]
            self.assertTrue(all(d < target for d in dates))
            for window in windows:
                expected = nmae([history[d][kind] for d in dates],
                                 [candidate_prediction(history, d, kind, window) for d in dates])
                self.assertAlmostEqual(info[f"{kind}_nmae_{prefix}{window}"], expected)
