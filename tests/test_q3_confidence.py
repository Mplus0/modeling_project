import unittest
from datetime import date, timedelta

import numpy as np

from src.q3.confidence import confidence


class ConfidenceTests(unittest.TestCase):
    def test_boundary_priority(self):
        target = date(2025, 3, 20)
        self.assertEqual(confidence(target, 18, {})["confidence_rho"], .5)
        zeros = dict(actual=np.zeros(144), old=np.ones(144), new=np.ones(144)*2)
        self.assertEqual(confidence(target, 18, {target-timedelta(days=1): zeros})["confidence_rho"], 0.)

    def test_mask_errors_and_window(self):
        target = date(2025, 3, 20)
        actual = np.zeros(144)
        actual[72:80] = 10
        old, new = actual.copy(), actual.copy()
        old[72:80] += 4
        new[72:80] += 2
        old[:72] = 1e9
        new[80:] = 1e9
        history = {target-timedelta(days=i): dict(actual=actual, old=old, new=new) for i in range(1,10)}
        result = confidence(target, 12, history)
        self.assertEqual(result["sample_count"], 7)
        self.assertEqual(result["effective_slots"], 56)
        self.assertAlmostEqual(result["historical_error_old"], .4)
        self.assertAlmostEqual(result["historical_error_new"], .2)
        self.assertAlmostEqual(result["confidence_rho"], 2/3)
        history[target] = history[target-timedelta(days=1)]
        with self.assertRaisesRegex(ValueError, "未来"):
            confidence(target, 12, history)

    def test_perfect_versions_neutral(self):
        curve = np.ones(144)
        result = confidence(date(2025,3,20), 6, {date(2025,3,19): dict(actual=curve,old=curve,new=curve)})
        self.assertEqual(result["confidence_rho"], .5)
