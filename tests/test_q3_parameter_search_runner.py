"""组级恢复、损坏重算及统一排名的合成运行管理测试。"""

import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd

from src.q3.parameters import PARAMETER_GRID
from src.q3.search_runner import read_group, persist_group, validate_group, run_search, validate_reference

ROOT = Path(__file__).resolve().parents[1]


class RunnerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder = ROOT/"outputs/q3/annual/reference_a0.90_l0.50"
        cls.daily = pd.read_csv(cls.folder/"q3_daily_metrics.csv",float_precision="round_trip")
        cls.metrics = json.loads((cls.folder/"q3_annual_metrics.json").read_text(encoding="utf-8"))

    def test_full_reference_revalidated(self):
        daily,metrics = validate_reference(self.folder)
        self.assertEqual(len(daily),334)
        self.assertEqual((metrics["alpha"],metrics["lambda"]),(.9,.5))

    def test_resume_rejects_corruption_and_wrong_signature(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            persist_group(folder,self.daily,self.metrics,"signature","reference")
            read_group(folder,.9,.5,"signature")
            with self.assertRaises(ValueError):
                read_group(folder,.9,.5,"changed")
            damaged = self.daily.copy()
            damaged.loc[0,"soc_start_kwh"] = 1200
            persist_group(folder,damaged,self.metrics,"signature","reference")
            with self.assertRaises(ValueError):
                read_group(folder,.9,.5,"signature")

    def test_metrics_and_status_corruption_rejected(self):
        for key,value in (("total_actual_cost_yuan",0),("run_label","FINAL"),("max_constraint_violation",.1),
                          ("simultaneous_slots",1),("alpha",.99)):
            altered = dict(self.metrics,**{key:value})
            with self.assertRaises(ValueError):
                validate_group(self.daily,altered,.9,.5)
        bad = copy.deepcopy(self.metrics)
        bad["solver_status_counts"]["actual_primary"] = {"optimal":48095}
        with self.assertRaises(ValueError):
            validate_group(self.daily,bad,.9,.5)

    def test_mock_twenty_groups_resume_ranking_and_ties(self):
        calls = []
        def runner(history,issues,price,dates,soc,alpha,weight,progress):
            self.assertEqual(soc,6000.)
            self.assertEqual(len(dates),334)
            calls.append((alpha,weight))
            d = self.daily.copy()
            d["alpha"],d["lambda"] = alpha,weight
            m = copy.deepcopy(self.metrics)
            m["alpha"],m["lambda"] = alpha,weight
            return {"daily_metrics":d,"mock_metrics":m},{"engine_runtime_seconds":1.}
        def writer(outputs,*args,**kwargs):
            return outputs["mock_metrics"]
        with tempfile.TemporaryDirectory() as tmp, patch("src.q3.search_runner.validate_reference",return_value=(self.daily,self.metrics)), patch("src.q3.search_runner.write_annual_outputs",side_effect=writer), patch("builtins.print"):
            root = Path(tmp)
            summary = run_search(root,None,None,None,"test",lambda:{"sha256_unchanged":True},runner)
            self.assertEqual(len(calls),19)
            self.assertEqual(summary["winner_count"],20)
            self.assertTrue(summary["all_groups_valid"])
            self.assertEqual(summary["best_score"],0.)
            run_search(root,None,None,None,"test",lambda:{"sha256_unchanged":True},runner)
            self.assertEqual(len(calls),19)
            damaged = root/"outputs/q3/search/groups/a0.80_l0.00/q3_daily_metrics.csv"
            damaged.write_text("broken",encoding="utf-8")
            run_search(root,None,None,None,"test",lambda:{"sha256_unchanged":True},runner)
            self.assertEqual(len(calls),20)
            self.assertEqual(calls[-1],(.8,0.))
            self.assertFalse(list((root/"outputs/q3/search/groups").rglob("q3_actual_schedule.csv")))

    def test_incomplete_mock_grid_cannot_score(self):
        with tempfile.TemporaryDirectory() as tmp, patch("src.q3.search_runner.validate_reference",return_value=(self.daily,self.metrics)), patch("builtins.print"):
            with self.assertRaisesRegex(ValueError,"20组"):
                run_search(Path(tmp),None,None,None,"test",lambda:{},grid=((.9,.5),))
