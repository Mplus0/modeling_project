"""固定价格复现及未来价格/负荷/PV扰动的端到端软件回归。"""
from datetime import date,timedelta
from pathlib import Path
import unittest
import numpy as np
import pandas as pd
from src.q2.optimizer import solve_plan
from src.q2.rolling import solve_actual_rolling_day
from src.q3.annual import HistoricalCache
from src.q3.simulation import simulate_day
from src.q4.inputs import load_inputs
from src.q4.q4_2 import ForecastCache,run_day as run_two
from src.q4.q4_3 import run_day as run_three
from src.q4.price_forecasting import PriceStream,forecast_price

ROOT = Path(__file__).resolve().parents[1]


class FixedStream(PriceStream):
    # 仅回归夹具：测试中人为固定预测和真实价格，不进入生产入口。
    @property
    def gamma(self):
        return 1.


class AdapterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.history,cls.prices,cls.issues = load_inputs(ROOT)
        cls.day = date(2025,3,20)
        cls.forecast,cls.risk,_ = ForecastCache(cls.history).prepare(cls.day)
        cls.load,cls.records,cls.residuals = HistoricalCache(cls.history,cls.issues).prepare(cls.day)
        cls.baseline,_ = forecast_price(cls.prices,cls.day)
        cls.fixed = pd.read_csv(ROOT/"data/processed/q1_input.csv",float_precision="round_trip").price_yuan_per_kwh.to_numpy()
        cls.observed = cls.history[cls.day]

    def q3(self,observe,baseline,**kwargs):
        return run_three(self.day,observe,float(self.history[self.day-timedelta(days=1)]["pv"][-1])*6,
                         self.load,baseline,self.issues,self.records,self.residuals,6000,.85,.25,"TEST ONLY",**kwargs)

    def test_q2_fixed_price_reproduces_original(self):
        obs = lambda s:(self.observed["load"][s-1],self.observed["pv"][s-1])
        plan,_ = solve_plan(self.forecast["load"]-self.forecast["pv"]+self.risk,self.forecast["pv"],self.fixed,6000,self.day)
        actual,_ = solve_actual_rolling_day(obs,self.forecast["load"],self.forecast["pv"],self.fixed,
                                          plan.grid_purchase_plan_kwh.to_numpy(),6000,self.day)
        q4 = run_two(self.day,lambda s:(*obs(s),self.fixed[s-1]),self.forecast,self.risk,self.fixed,6000,"TEST ONLY",FixedStream)
        for column in ("x_real_kwh","y_real_kwh","q_real_kwh","z_real_kwh","soc_real_end_kwh","emergency_purchase_kwh","total_cost_slot_yuan"):
            np.testing.assert_allclose(q4["actual_schedule"][column],actual[column],rtol=0,atol=1e-6)
        np.testing.assert_allclose(q4["plan_schedule"].grid_purchase_plan_kwh,plan.grid_purchase_plan_kwh,atol=1e-6,rtol=0)

    def test_q3_fixed_price_reproduces_original(self):
        obs = lambda s:(self.observed["load"][s-1],self.observed["pv"][s-1])
        original = simulate_day(self.day,obs,float(self.history[self.day-timedelta(days=1)]["pv"][-1])*6,
                               self.load,self.fixed,self.issues,self.records,self.residuals,6000,.85,.25)
        q4 = self.q3(lambda s:(*obs(s),self.fixed[s-1]),self.fixed,stream_factory=FixedStream)
        for name,columns in (("actual_schedule",["x_real_kwh","y_real_kwh","q_real_kwh","z_real_kwh","soc_real_end_kwh","emergency_purchase_kwh"]),
                             ("plan_updates",["new_plan_kwh","increase_kwh","decrease_kwh","plan_terminal_soc_kwh"]),
                             ("daily_metrics",["total_actual_cost_yuan","actual_throughput_kwh"])):
            np.testing.assert_allclose(q4[name][columns],original[name][columns],atol=1e-6,rtol=0)

    def test_future_price_load_pv_cannot_change_current_decisions(self):
        def observe(s,changed=False):
            scale = 1.7 if changed and s>40 else 1.
            return (self.observed["load"][s-1]*scale,self.observed["pv"][s-1]*scale,self.prices[self.day][s-1]*scale)
        for variant in (2,3):
            def run(changed):
                callback = lambda s:observe(s,changed)
                return (run_two(self.day,callback,self.forecast,self.risk,self.baseline,6000,"TEST ONLY")
                        if variant==2 else self.q3(callback,self.baseline))
            before,after = run(False),run(True)
            cols = ["x_real_kwh","y_real_kwh","q_real_kwh","z_real_kwh","emergency_purchase_kwh","soc_real_end_kwh"]
            np.testing.assert_allclose(before["actual_schedule"].iloc[:40][cols],after["actual_schedule"].iloc[:40][cols],rtol=0,atol=1e-6)
            if variant==3:
                # 06:10等普通执行时刻只刷新价格，不更改06:00已经确定的合同。
                plan = before["plan_updates"].loc[lambda p:p.update_time.eq("06:00")]
                np.testing.assert_allclose(before["actual_schedule"].grid_purchase_plan_kwh.iloc[36:72],plan.new_plan_kwh.iloc[:36],atol=1e-6,rtol=0)
                self.assertEqual(before["plan_updates"].groupby("update_time").size().tolist(),[144,108,72,36])
                self.assertEqual(len(before["price_refresh"]),144)

    def test_saved_smoke_three_days_and_integrity(self):
        from src.q4.metrics import load_outputs
        from src.q4.validation import validate_outputs
        from src.q4.inputs import frozen_hashes
        import json
        for variant in (2,3):
            outputs,metrics = load_outputs(ROOT/f"outputs/q4/smoke/q4_{variant}")
            check = validate_outputs(outputs,variant)
            self.assertEqual(check["days"],3)
            self.assertEqual(check["slots"],432)
            self.assertLessEqual(check["cross_day_soc_max_difference"],1e-6)
            self.assertFalse(metrics["formal"])
        before = json.loads((ROOT/"outputs/q4/frozen_sha256_before.json").read_text(encoding="utf-8"))
        self.assertEqual(frozen_hashes(ROOT),before)
