"""光伏首小时锚点、普通插值、发布时间与已执行时段冻结测试。"""

import unittest

import numpy as np
import pandas as pd

from src.q3.forecast import fuse_remaining, interpolate_issue


class ForecastTests(unittest.TestCase):
    def issue(self):
        issue = pd.Timestamp("2025-03-20 12:00")
        table = pd.DataFrame({"issue_datetime": issue,
                              "target_datetime": pd.date_range(issue + pd.Timedelta(hours=1), periods=24, freq="h"),
                              "horizon_hour": range(1, 25), "pv_forecast_kw": np.arange(1, 25)*600.})
        return issue, table

    def test_first_hour_observed_anchor_and_energy(self):
        issue, table = self.issue()
        targets = pd.date_range(issue + pd.Timedelta(minutes=10), periods=6, freq="10min")
        actual = interpolate_issue(table, issue, 0., targets)
        np.testing.assert_allclose(actual, np.arange(1, 7)*100/6)
        anchored = interpolate_issue(table, issue, 300., targets)
        np.testing.assert_allclose(anchored, np.arange(350, 601, 50)/6)

    def test_ordinary_hour_and_wrong_issue(self):
        issue, table = self.issue()
        result = interpolate_issue(table, issue, 0., [issue + pd.Timedelta(minutes=90)])
        self.assertAlmostEqual(result[0], 900/6)
        with self.assertRaisesRegex(ValueError, "发布时间"):
            interpolate_issue(table, issue+pd.Timedelta(hours=6), 0., [issue+pd.Timedelta(hours=7)])

    def test_only_unexecuted_slots_change(self):
        old = np.arange(144, dtype=float)
        for first in (37, 73, 109):
            result = fuse_remaining(old, np.zeros(145-first), first, .25)
            np.testing.assert_array_equal(result[:first-1], old[:first-1])
            np.testing.assert_allclose(result[first-1:], old[first-1:]*.75)
        np.testing.assert_array_equal(old, np.arange(144))
