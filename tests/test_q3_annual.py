"""年度缓存因果性、旧回放等价及保存结果独立验收。"""

from datetime import date
from pathlib import Path
from unittest.mock import patch
import json
import unittest

import numpy as np
import pandas as pd

from src.q2.forecasting import load_daily_inputs
from src.q3.forecast import load_hourly_forecasts, replay_history, load_prediction, update_pv
from src.q3.scenarios import build_scenarios
from src.q3.annual import HistoricalCache, FORMAL_DATES, run_dates, validate_annual, ANNUAL_LABEL
from src.q3.optimizer import solve_actual_step
from src.q3.search import score_annual_results
from src.common.data_loader import file_hash

ROOT = Path(__file__).resolve().parents[1]


class AnnualTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.history,cls.price = load_daily_inputs(ROOT/"data/processed/historical_power.csv",ROOT/"data/processed/q1_input.csv")
        cls.issues = load_hourly_forecasts(ROOT/"data/processed/pv_forecast_hourly.csv")

    def test_dates_and_early_scenario_counts(self):
        self.assertEqual(len(FORMAL_DATES),334)
        self.assertEqual((FORMAL_DATES[0],FORMAL_DATES[-1]),(date(2025,2,1),date(2025,12,31)))
        cache = HistoricalCache(self.history,self.issues)
        for i,day in enumerate(FORMAL_DATES[:15]):
            _,records,residuals = cache.prepare(day)
            self.assertEqual(len(residuals),min(14,i+2))
            self.assertTrue(all(d<day for d in residuals))
            self.assertTrue(all(d<day for d in records))
        self.assertEqual(cache.replayed_days,45)

    def test_cache_matches_replay_and_all_updates(self):
        day = date(2025,3,20)
        prior = {d:v for d,v in self.history.items() if d<day}
        residuals,records = replay_history(prior,day,self.issues)
        load,_ = load_prediction(prior,day)
        cached_load,cached_records,cached_residuals = HistoricalCache(self.history,self.issues).prepare(day)
        np.testing.assert_array_equal(load,cached_load)
        self.assertEqual(sorted(cached_residuals),sorted(residuals)[-14:])
        old,old_cached = None,None
        for hour in (0,6,12,18):
            anchor = self.history[date(2025,3,19)]["pv"][-1] if hour==0 else self.history[day]["pv"][hour*6-1]
            old,raw,conf = update_pv(day,hour,anchor*6,old,self.issues,records)
            old_cached,raw_cached,conf_cached = update_pv(day,hour,anchor*6,old_cached,self.issues,cached_records)
            np.testing.assert_array_equal(old,old_cached)
            np.testing.assert_array_equal(raw,raw_cached)
            self.assertEqual(conf,conf_cached)
            scenario = build_scenarios(day,hour,load,old,residuals,hour*6+1)
            cached = build_scenarios(day,hour,cached_load,old_cached,cached_residuals,hour*6+1)
            self.assertEqual(scenario["dates"],cached["dates"])
            for key in ("load","pv","probability"):
                np.testing.assert_array_equal(scenario[key],cached[key])

    def test_annual_path_future_actual_does_not_change_current_decision(self):
        day = date(2025,3,20)
        changed = dict(self.history)
        changed[day] = {k:np.array(v,copy=True) for k,v in self.history[day].items()}
        for key in ("load","pv"):
            changed[day][key][40:] += 1000
        class ProbeComplete(Exception):
            pass
        def probe(history):
            actions = []
            def solve(*args,**kwargs):
                if args[0]>40:
                    raise ProbeComplete()
                frame,check = solve_actual_step(*args,**kwargs)
                actions.append(frame.iloc[0].to_dict())
                return frame,check
            with patch("src.q3.simulation.solve_actual_step",side_effect=solve):
                with self.assertRaises(ProbeComplete):
                    run_dates(history,self.issues,self.price,[day],6000,.90,.5)
            return pd.DataFrame(actions)
        pd.testing.assert_frame_equal(probe(self.history),probe(changed),check_exact=True)

    def test_saved_annual_validation_and_single_group_score_rejected(self):
        folder = ROOT/"outputs/q3/annual/reference_a0.90_l0.50"
        if not (folder/"q3_annual_metrics.json").exists():
            self.skipTest("正式全年参考尚未运行")
        names = ("actual_schedule","daily_metrics","forecast_updates","confidence","plan_updates","scenarios_summary")
        outputs = {k:pd.read_csv(folder/f"q3_{k}.csv",float_precision="round_trip") for k in names}
        validate_annual(outputs)
        metrics = json.loads((folder/"q3_annual_metrics.json").read_text(encoding="utf-8"))
        self.assertEqual(metrics["run_label"],ANNUAL_LABEL)
        self.assertEqual(metrics["slots"],48096)
        self.assertEqual(metrics["days"],334)
        self.assertTrue(all(file_hash(ROOT/p)==h for p,h in metrics["integrity"]["sha256"].items()))
        with self.assertRaisesRegex(ValueError,"20组"):
            score_annual_results(outputs["daily_metrics"])
        malformed = {**outputs,"actual_schedule":outputs["actual_schedule"].copy()}
        malformed["actual_schedule"].loc[1,"slot"] = 1
        with self.assertRaisesRegex(ValueError,"重复"):
            validate_annual(malformed)
