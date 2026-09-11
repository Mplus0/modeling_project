from datetime import date
import unittest
import numpy as np
from pathlib import Path
import pandas as pd

from src.q2.risk import empirical_quantile_type1, historical_risk


class RiskTests(unittest.TestCase):
    def test_full_year_online_quantiles(self):
        folder = Path(__file__).resolve().parents[1] / "outputs/q2"
        warm = pd.read_csv(folder / "q2_warmup_predictions.csv", float_precision="round_trip")
        predictions = pd.read_csv(folder / "q2_predictions.csv", float_precision="round_trip")
        self.assertEqual(warm.date.unique().tolist(), ["2025-01-30", "2025-01-31"])
        errors = [g.baseline_error_kwh.to_numpy() for _, g in warm.groupby("date", sort=True)]
        for _, group in predictions.groupby("date", sort=True):
            self.assertTrue((group.historical_error_sample_count == len(errors)).all())
            expected = empirical_quantile_type1(errors)
            np.testing.assert_allclose(group.risk_quantile_kwh, expected, rtol=0, atol=1e-9)
            np.testing.assert_allclose(group.risk_adjusted_net_load_kwh,
                                       group.baseline_net_load_kwh + expected, rtol=0, atol=1e-9)
            errors.append((group.load_actual_kwh - group.pv_actual_kwh - group.baseline_net_load_kwh).to_numpy())

    def test_type1_index_no_interpolation(self):
        self.assertEqual(empirical_quantile_type1([1, 2, 3, 4, 100]), 4)
        self.assertEqual(empirical_quantile_type1([1, 100]), 100)
        self.assertEqual(empirical_quantile_type1([9]), 9)

    def test_negative_remains_negative(self):
        risk = empirical_quantile_type1([-10, -9, -8, -7, -6])
        self.assertEqual(risk, -7)
        self.assertLess(-5 + risk, 0)

    def test_dates_and_empty(self):
        residuals = {date(2025, 1, 30): np.full(144, -2.), date(2025, 1, 31): np.full(144, 3.)}
        risk, dates = historical_risk(residuals, date(2025, 2, 1))
        self.assertEqual(len(dates), 2)
        np.testing.assert_array_equal(risk, np.full(144, 3.))
        with self.assertRaises(ValueError):
            historical_risk(residuals, date(2025, 1, 31))
        with self.assertRaises(ValueError):
            historical_risk({}, date(2025, 2, 1))
