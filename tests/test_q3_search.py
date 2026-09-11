import unittest
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from src.q3.parameters import ALPHA_CHOICES, LAMBDA_CHOICES, PARAMETER_GRID
from src.q3.search import score_annual_results
from src.q3.optimizer import empirical_cvar


class SearchTests(unittest.TestCase):
    def data(self):
        dates = pd.date_range("2025-02-01", "2025-12-31")
        return pd.concat([pd.DataFrame(dict(alpha=a, **{"lambda":w}, date=dates,
                                            total_actual_cost_yuan=100.+i*(np.arange(334)%2),
                                            emergency_slot_count=i))
                          for i,(a,w) in enumerate(PARAMETER_GRID)],ignore_index=True)

    def test_choices_and_fourteen_scenario_tail(self):
        self.assertEqual(ALPHA_CHOICES,(.8,.85,.9,.95))
        self.assertEqual(LAMBDA_CHOICES,(0,.25,.5,1,2))
        self.assertEqual(len(set(PARAMETER_GRID)),20)
        losses = np.arange(14.)
        cvars = [empirical_cvar(losses,a) for a in ALPHA_CHOICES]
        self.assertTrue(all(a<b for a,b in zip(cvars,cvars[1:])))
        self.assertEqual(cvars[-1],13.)
        root = Path(__file__).resolve().parents[1]
        rejected = subprocess.run([sys.executable,str(root/"scripts/07_run_q3_single.py"),
                                   "--alpha","0.99","--lambda","0.5"],capture_output=True,text=True)
        self.assertEqual(rejected.returncode,2)
        self.assertIn("invalid choice",rejected.stderr)

    def test_all_twenty_global_bounds_and_population_std(self):
        data = self.data()
        scored, winners = score_annual_results(data)
        np.testing.assert_allclose(scored.Score,np.arange(20)/19,atol=1e-12)
        np.testing.assert_allclose(scored.daily_cost_std,np.arange(20)/2)
        self.assertEqual(winners.to_dict("records"),[{"alpha":.8,"lambda":0.}])
        pd.testing.assert_frame_equal(data,self.data())

    def test_constant_and_near_constant_metrics(self):
        data = self.data()
        data["total_actual_cost_yuan"] = 100.
        data["emergency_slot_count"] = 0
        data.loc[data.alpha.eq(.95),"total_actual_cost_yuan"] += 1e-10
        scored,winners = score_annual_results(data)
        self.assertTrue(scored.Score.eq(0).all())
        self.assertEqual(len(winners),20)

    def test_incomplete_duplicate_and_old_alpha_rejected(self):
        data = self.data()
        for broken in (data.iloc[:-1], data.iloc[334:], pd.concat([data,data.iloc[:1]]),
                       data.assign(alpha=data.alpha.replace(.95,.99))):
            with self.assertRaises(ValueError):
                score_annual_results(broken)
