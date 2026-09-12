"""已确认SCIP合同负尾差的边界回归，不修改冻结Q3非负规则。"""
from pathlib import Path
import unittest
import numpy as np
from src.q3.optimizer import VALIDATION_TOL,solve_actual_step
from src.q4.q4_3 import normalize_commitment,solve_actual_tolerant

ROOT = Path(__file__).resolve().parents[1]


class CommitmentBoundaryTests(unittest.TestCase):
    def test_only_authorized_roundoff_is_normalized(self):
        original = np.array([-1e-10,-.5*VALIDATION_TOL,-VALIDATION_TOL,0.,2.])
        saved = original.copy()
        np.testing.assert_array_equal(normalize_commitment(original),[0.,0.,0.,0.,2.])
        np.testing.assert_array_equal(original,saved)
        for negative in (-1.01*VALIDATION_TOL,-1.,float("nan")):
            with self.assertRaises(ValueError):
                normalize_commitment([negative])

    def test_real_negative_inputs_still_rejected_with_context(self):
        for key in ("load_forecast","pv_forecast","price","commitment"):
            values = {k:np.ones(2) for k in ("load_forecast","pv_forecast","price","commitment")}
            values[key][0] = -2*VALIDATION_TOL if key=="commitment" else -1e-10
            with self.assertRaises(ValueError) as caught:
                solve_actual_tolerant(1,1.,0.,**values,current_soc=6000.,plan_terminal_soc=6000.,date="2025-09-22")
            message = str(caught.exception)
            for text in ("2025-09-22","slot=1","load_forecast","pv_forecast","price","commitment"):
                self.assertIn(text,message)

    def test_exact_failure_snapshot_now_solves(self):
        with np.load(ROOT/"outputs/q4/diagnostics/last_negative_input.npz") as data:
            args = {k:data[k].item() if data[k].ndim==0 else data[k].copy() for k in data.files}
        self.assertEqual(args["date"],"2025-09-22")
        self.assertEqual(args["current_slot"],109)
        self.assertEqual(float(args["commitment"].min()),-1.1368683772161603e-13)
        with self.assertRaisesRegex(ValueError,"必须非负"):
            solve_actual_step(**args)
        frame,check = solve_actual_tolerant(**args)
        self.assertEqual(len(frame),36)
        self.assertTrue(all(check[f"{stage}_status"]=="optimal" for stage in ("primary","secondary","tertiary")))
        self.assertLessEqual(check["max_violation"],VALIDATION_TOL)

    def test_failed_day_with_recorded_initial_soc(self):
        from datetime import date,timedelta
        from src.q4.inputs import load_inputs
        from src.q3.annual import HistoricalCache
        from src.q4.price_forecasting import forecast_price
        from src.q4.q4_3 import run_day
        history,prices,issues = load_inputs(ROOT)
        day = date(2025,9,22)
        load,records,residuals = HistoricalCache(history,issues).prepare(day)
        baseline,_ = forecast_price(prices,day)
        observed = history[day]
        result = run_day(day,lambda s:(observed["load"][s-1],observed["pv"][s-1],prices[day][s-1]),
                         history[day-timedelta(days=1)]["pv"][-1]*6,load,baseline,issues,records,residuals,
                         1371.8898963228062,.8,0.,"FAILURE DAY REPLAY ONLY")
        plans = result["plan_updates"]
        self.assertGreater(int((plans.solver_grid_raw_kwh<0).sum()),0)
        self.assertTrue((plans.new_plan_kwh>=0).all())
        self.assertLessEqual(float(plans.commitment_roundoff_adjustment_kwh.max()),VALIDATION_TOL)
        self.assertEqual(len(result["actual_schedule"]),144)
        self.assertLessEqual(float(result["daily_metrics"].max_constraint_violation.iloc[0]),VALIDATION_TOL)
