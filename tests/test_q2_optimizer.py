import unittest
import numpy as np
from pathlib import Path
import pandas as pd

from src.q2.optimizer import INITIAL_SOC, solve_actual, solve_plan, validate_schedule


class OptimizerTests(unittest.TestCase):
    def test_full_year_csv_integration(self):
        output = Path(__file__).resolve().parents[1] / "outputs/q2"
        plan = pd.read_csv(output / "q2_plan_schedule.csv", float_precision="round_trip")
        actual = pd.read_csv(output / "q2_actual_schedule.csv", float_precision="round_trip")
        daily = pd.read_csv(output / "q2_daily_metrics.csv", float_precision="round_trip")
        self.assertEqual(len(actual), 48096)
        self.assertEqual(len(plan), 48096)
        self.assertEqual(len(daily), 334)
        self.assertEqual(actual.soc_real_start_kwh.iloc[0], 6000.)
        np.testing.assert_allclose(daily.soc_start_kwh.iloc[1:], daily.soc_actual_end_kwh.iloc[:-1], rtol=0, atol=1e-6)
        np.testing.assert_array_equal(plan.grid_purchase_plan_kwh, actual.grid_purchase_plan_kwh)
        self.assertTrue((abs(daily.soc_actual_end_kwh - daily.soc_start_kwh) > 1).any())
        for index, row in daily.iterrows():
            for mode, table in [("plan", plan), ("actual", actual)]:
                checked = validate_schedule(table.iloc[index * 144:(index + 1) * 144], mode, row.soc_start_kwh,
                                            row[f"{mode}_primary_star"], row[f"{mode}_secondary_objective"])
                self.assertLessEqual(checked["max_violation"], 1e-6)

    def test_plan_terminal_and_cost_lock(self):
        frame, checked = solve_plan(np.array([10., 10.]), np.zeros(2), np.array([1., 10.]), 1200., "test")
        self.assertAlmostEqual(frame.soc_plan_end_kwh.iloc[-1], 1200., delta=1e-6)
        self.assertLessEqual(checked["max_violation"], 1e-6)
        self.assertAlmostEqual(frame.planned_cost_slot_yuan.sum(), checked["primary_star"], delta=1e-6)
        self.assertEqual((checked["primary_status"], checked["secondary_status"]), ("optimal", "optimal"))

    def test_actual_cost_priority_and_no_terminal_reset(self):
        commitment = np.zeros(2)
        frame, checked = solve_actual(np.array([10., 10.]), np.zeros(2), np.array([1., 10.]), 1210., commitment, "test")
        np.testing.assert_allclose(frame.x_real_kwh + frame.y_real_kwh, commitment, atol=1e-6)
        # 仅9kWh可送达负荷，应该先替代高价时段紧急购电：费用=5*(10+10*1)。
        self.assertAlmostEqual(checked["primary_star"], 100., delta=1e-6)
        self.assertAlmostEqual(frame.soc_real_end_kwh.iloc[-1], 1200., delta=1e-6)
        self.assertAlmostEqual(frame.emergency_purchase_kwh.sum(), 11., delta=1e-6)
        self.assertLessEqual(checked["max_violation"], 1e-6)
        np.testing.assert_array_less(frame.q_real_kwh.to_numpy(), np.full(2, 1e-6))
        following, _ = solve_plan(np.zeros(2), np.zeros(2), np.ones(2), frame.soc_real_end_kwh.iloc[-1], "next")
        self.assertEqual(following.soc_plan_start_kwh.iloc[0], frame.soc_real_end_kwh.iloc[-1])
        self.assertEqual(INITIAL_SOC, 6000)

    def test_negative_risk_and_constraints(self):
        frame, checked = solve_plan(np.array([-30., -20.]), np.array([30., 20.]), np.ones(2), 6000., "test")
        self.assertAlmostEqual(checked["cost"], 0, delta=1e-6)
        self.assertLessEqual(checked["max_violation"], 1e-6)
        broken = frame.copy()
        broken.loc[0, "x_plan_kwh"] = 1000
        self.assertGreater(validate_schedule(broken, "plan", 6000., checked["primary_star"], checked["secondary_objective"])["max_violation"], 1)
