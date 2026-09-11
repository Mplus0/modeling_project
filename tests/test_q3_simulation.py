import unittest
import json
from pathlib import Path
from datetime import date, timedelta
from unittest.mock import patch

import numpy as np
import pandas as pd

from src.q3.simulation import expected_terminal_soc, simulate_day, simulate_days
from src.q3.optimizer import validate_schedule, VALIDATION_TOL
from src.common.data_loader import file_hash


class SimulationTests(unittest.TestCase):
    def test_probability_weighted_target(self):
        self.assertEqual(expected_terminal_soc([1200,1300],[.5,.5]),1250)
        self.assertEqual(expected_terminal_soc([1200,1400],[.25,.75]),1350)
        for probabilities in ([.2,.3],[-.1,1.1],[1.], [float("nan"),1.]):
            with self.assertRaisesRegex(ValueError,"概率"):
                expected_terminal_soc([1200,1300],probabilities)

    def test_four_updates_and_observation_order(self):
        day = date(2025,3,20)
        issues = {}
        for hour in (0,6,12,18):
            issue = pd.Timestamp(day)+pd.Timedelta(hours=hour)
            issues[issue] = pd.DataFrame(dict(issue_datetime=issue,
                                             target_datetime=pd.date_range(issue+pd.Timedelta(hours=1),periods=24,freq="h"),
                                             horizon_hour=range(1,25),pv_forecast_kw=np.zeros(24)))
        residuals = {day-timedelta(days=1):dict(load=np.zeros(144),pv={h:np.zeros(144) for h in (0,6,12,18)})}
        calls = []
        def observe(slot):
            self.assertEqual(slot,len(calls)+1)
            calls.append(slot)
            return 0.,0.
        result = simulate_day(day,observe,0,np.zeros(144),np.ones(144),issues,{},residuals,6000,.95,.5)
        self.assertEqual(calls,list(range(1,145)))
        self.assertEqual(len(result["actual_schedule"]),144)
        plans = result["plan_updates"]
        self.assertEqual(plans.groupby("update_time").size().tolist(),[144,108,72,36])
        self.assertEqual(result["confidence"].confidence_rho.tolist(),[.5,.5,.5])
        self.assertAlmostEqual(result["daily_metrics"].soc_end_kwh.iloc[0],6000)
        self.assertFalse(any(f.isna().any().any() for f in result.values()))

    def test_only_first_day_artificial_initialization(self):
        day = date(2025,3,20)
        h = {day+timedelta(days=i):dict(pv=np.zeros(144),load=np.zeros(144),source_time=np.arange(144)) for i in range(-1,3)}
        received = []
        def run(*args):
            start = args[8]
            received.append(start)
            return dict(actual_schedule=pd.DataFrame(dict(soc_real_end_kwh=np.full(144,start-100))))
        with patch("src.q3.simulation.replay_history",return_value=({},{})), patch("src.q3.simulation.load_prediction",return_value=(np.zeros(144),{})), patch("src.q3.simulation.simulate_day",side_effect=run):
            simulate_days(h,{},np.ones(144),day,3,6000,.95,.5)
        self.assertEqual(received,[6000,5900,5800])


class SavedReferenceTests(unittest.TestCase):
    def test_three_day_outputs_independently(self):
        root = Path(__file__).resolve().parents[1]
        output = root/"outputs/q3/single"
        if not (output/"q3_single_metrics.json").exists():
            self.skipTest("先运行三日参考验证生成输出")
        read = lambda name: pd.read_csv(output/f"q3_{name}.csv",float_precision="round_trip")
        actual, plans, scenarios, daily = [read(k) for k in ("actual_schedule","plan_updates","scenarios_summary","daily_metrics")]
        self.assertEqual(len(actual),432)
        self.assertFalse(actual.duplicated(["date","slot"]).any())
        self.assertFalse(any(f.isna().any().any() for f in (actual,plans,scenarios,daily)))
        for name in ("rolling_primary_status","rolling_secondary_status","rolling_tertiary_status"):
            self.assertTrue(actual[name].eq("optimal").all())
        self.assertTrue(plans.primary_status.eq("optimal").all())
        self.assertTrue(plans.secondary_status.eq("optimal").all())
        for (day,hour), group in scenarios.groupby(["date","update_time"]):
            self.assertEqual(len(group),14)
            self.assertTrue((group.history_date<day).all())
            expected = float(group.probability@group.terminal_soc_kwh)
            plan = plans[(plans.date==day)&(plans.update_time==hour)]
            np.testing.assert_allclose(plan.plan_terminal_soc_kwh,expected,atol=1e-6,rtol=0)
            start = int(hour[:2])*6+1
            executed = actual[(actual.date==day)&actual.slot.between(start,start+35)]
            np.testing.assert_allclose(executed.plan_terminal_soc_kwh,expected,atol=1e-6,rtol=0)
            np.testing.assert_allclose(executed.effective_contract_kwh,plan.new_plan_kwh.iloc[:36],atol=1e-6,rtol=0)
            if start>1:
                previous_hour = f"{int(hour[:2])-6:02d}:00"
                previous = plans[(plans.date==day)&(plans.update_time==previous_hour)&(plans.slot>=start)]
                np.testing.assert_allclose(plan.previous_plan_kwh,previous.new_plan_kwh,atol=1e-6,rtol=0)
        for i,row in daily.iterrows():
            frame = actual[actual.date==row.date]
            check = validate_schedule(frame,"actual",row.soc_start_kwh)
            self.assertLessEqual(check["max_violation"],VALIDATION_TOL)
            self.assertAlmostEqual(check["cost"],row.actual_emergency_cost_yuan,places=6)
            self.assertAlmostEqual(row.total_actual_cost_yuan,row.plan_cost_00_yuan+row.adjustment_cost_total_yuan+check["cost"],places=6)
            if i:
                self.assertEqual(row.soc_start_kwh,daily.soc_end_kwh.iloc[i-1])
        metrics = json.loads((output/"q3_single_metrics.json").read_text(encoding="utf-8"))
        self.assertTrue(all(file_hash(root/p)==h for p,h in metrics["integrity"]["sha256"].items()))
        # 单日与三日运行首日逐值一致，追加后续真实日期不能反向影响首日。
        one = pd.read_csv(output/"smoke_one_day/q3_actual_schedule.csv",float_precision="round_trip")
        pd.testing.assert_frame_equal(one,actual.iloc[:144].reset_index(drop=True))