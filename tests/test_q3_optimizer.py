import unittest

import numpy as np

from src.q3.optimizer import empirical_cvar, solve_plan, solve_actual_step, VALIDATION_TOL


class PlanTests(unittest.TestCase):
    def test_cvar_fractional_tail_and_invalid_alpha(self):
        self.assertAlmostEqual(empirical_cvar([0,10,20,30], .5),25)
        self.assertAlmostEqual(empirical_cvar([0,10,20,30], .625),80/3)
        self.assertAlmostEqual(empirical_cvar([0,10,20,30], .95),30)
        with self.assertRaises(ValueError):
            empirical_cvar([1,2],1)

    def test_plan_no_terminal_restore(self):
        result = solve_plan([[100]],[[0]],[1],6000,.95,.5)
        self.assertLess(abs(result["primary_star"]), VALIDATION_TOL)
        self.assertAlmostEqual(result["scenario_terminal_soc"][0],6000-100/.9,places=5)
        self.assertEqual(result["primary_status"],"optimal")
        self.assertEqual(result["secondary_status"],"optimal")
        self.assertLessEqual(result["max_violation"],VALIDATION_TOL)

    def test_adjustment_and_fixed_shared_grid(self):
        previous = np.array([100.])
        result = solve_plan([[0],[0]],[[0],[0]],[2],1200,.95,.5,previous)
        self.assertAlmostEqual(result["purchase_or_adjustment_cost"],-100,places=5)
        self.assertAlmostEqual(result["decrease"][0],100,places=5)
        np.testing.assert_array_equal(previous,[100.])
        for frame in result["scenario_schedules"]:
            np.testing.assert_allclose(frame.x_real_kwh+frame.y_real_kwh,result["grid"],atol=VALIDATION_TOL)
        increased = solve_plan([[100]],[[0]],[2],1200,.95,.5,[0])
        self.assertAlmostEqual(increased["purchase_or_adjustment_cost"],300,places=5)

    def test_lambda_zero(self):
        result = solve_plan([[0],[100]],[[0],[0]],[1],1200,.95,0)
        self.assertAlmostEqual(result["primary_objective"],
                               result["purchase_or_adjustment_cost"]+result["expected_emergency_cost"],places=6)


class ActualTests(unittest.TestCase):
    def solve(self, start, target, load=0, pv=0, grid=0):
        return solve_actual_step(1,load,pv,[load],[pv],[1],[grid],start,target,"TEST / REFERENCE ONLY")

    def test_absolute_gap_both_directions_and_latest_target(self):
        frame, check = self.solve(6000,5900)
        self.assertAlmostEqual(frame.soc_real_end_kwh.iloc[-1],5900,places=5)
        self.assertAlmostEqual(frame.z_real_kwh.iloc[0],90,places=5)
        self.assertAlmostEqual(check["terminal_gap"],0,places=5)
        # 高于当前状态的目标也必须被跟踪，不能仅实现Q2的单侧缺口。
        frame, check = self.solve(6000,6090,pv=100)
        self.assertAlmostEqual(frame.q_real_kwh.iloc[0],100,places=5)
        self.assertAlmostEqual(frame.soc_real_end_kwh.iloc[-1],6090,places=5)
        self.assertEqual([check[k] for k in ("primary_status","secondary_status","tertiary_status")],["optimal"]*3)

    def test_emergency_cost_has_priority_over_target(self):
        frame, check = self.solve(6000,6000,load=100)
        self.assertLess(abs(check["primary_star"]),VALIDATION_TOL)
        self.assertAlmostEqual(frame.z_real_kwh.iloc[0],100,places=5)
        self.assertAlmostEqual(check["terminal_gap"],100/.9,places=5)

    def test_explicit_current_observation_future_forecasts_only(self):
        forecast = np.array([999.,100.])
        frame, check = solve_actual_step(1,20,0,forecast,[0,0],[1,1],[0,0],6000,5800,"TEST")
        np.testing.assert_array_equal(frame.load_actual_kwh,[20,100])
        np.testing.assert_array_equal(forecast,[999,100])
        self.assertLessEqual(check["max_violation"],VALIDATION_TOL)
