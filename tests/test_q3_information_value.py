"""独立诊断只固定合同，不固定场景追索决策。"""
import unittest
import json
from pathlib import Path
import numpy as np
import pandas as pd
from src.analysis.q3_information_value import (
    solve_fixed_grid_diagnostic, solve_plan, ALPHA, WEIGHT,
    VALIDATION_TOL, require_value, previous_contract, read_final,
)


class InformationValueTests(unittest.TestCase):
    def test_no_adjustment_value_zero(self):
        zero = np.zeros((1,1))
        fixed = solve_fixed_grid_diagnostic(zero,zero,np.ones(1),1200.,np.zeros(1))
        roll = solve_plan(zero,zero,np.ones(1),1200.,ALPHA,WEIGHT,np.zeros(1))
        self.assertLessEqual(abs(fixed['primary_objective']-roll['primary_objective']),VALIDATION_TOL)

    def test_beneficial_adjustment_positive(self):
        load, pv = np.array([[100.]]), np.zeros((1,1))
        fixed = solve_fixed_grid_diagnostic(load,pv,np.ones(1),1200.,np.zeros(1))
        roll = solve_plan(load,pv,np.ones(1),1200.,ALPHA,WEIGHT,np.zeros(1))
        self.assertGreater(fixed['primary_objective']-roll['primary_objective'],100.)

    def test_fixed_contract_leaves_recourse_free(self):
        result = solve_fixed_grid_diagnostic(np.array([[10.],[100.]]),np.zeros((2,1)),np.ones(1),1200.,np.array([20.]))
        np.testing.assert_allclose(result['grid'],[20.],atol=VALIDATION_TOL,rtol=0)
        np.testing.assert_allclose(result['increase'],0,atol=VALIDATION_TOL,rtol=0)
        np.testing.assert_allclose(result['decrease'],0,atol=VALIDATION_TOL,rtol=0)
        self.assertEqual(result['primary_status'],'optimal')
        self.assertLessEqual(result['max_violation'],VALIDATION_TOL)
        schedules = result['scenario_schedules']
        self.assertGreater(float(schedules[1]['emergency_purchase_kwh'].sum())-float(schedules[0]['emergency_purchase_kwh'].sum()),70.)

    def test_significant_negative_value_rejected(self):
        with self.assertRaisesRegex(ValueError,'J_roll'):
            require_value(-2*VALIDATION_TOL)
        require_value(-.5*VALIDATION_TOL)
        with self.assertRaisesRegex(ValueError,'有限'):
            require_value(float('nan'))

    def test_previous_contract_is_latest_completed_plan(self):
        rows = [dict(update_time=f'{hour:02d}:00',slot=slot,new_plan_kwh=hour+1.,previous_plan_kwh=hour-5.)
                for hour in (0,6,12,18) for slot in range(hour*6+1,145)]
        plans = pd.DataFrame(rows)
        for hour in (6,12,18):
            values,_ = previous_contract(plans,hour)
            np.testing.assert_array_equal(values,np.full(144-hour*6,hour-5.))

    def test_saved_diagnostics_independently(self):
        root = Path(__file__).resolve().parents[1]
        folder = root/'outputs/q3/diagnostics/information_value'
        if not (folder/'q3_information_value_by_update.csv').exists():
            self.skipTest('尚未生成1002条诊断输出')
        read_final(root)
        table = pd.read_csv(folder/'q3_information_value_by_update.csv',float_precision='round_trip')
        self.assertEqual(len(table),1002)
        self.assertFalse(table.duplicated(['date','update_time']).any())
        self.assertEqual(table.groupby('update_time').size().to_dict(),{'06:00':334,'12:00':334,'18:00':334})
        self.assertFalse(table.drop(columns='relative_value_percent').isna().any().any())
        np.testing.assert_allclose(table.J_fix_yuan-table.J_roll_yuan,table.V_yuan,atol=VALIDATION_TOL,rtol=0)
        np.testing.assert_allclose(table.J_fix_yuan,table.fixed_expected_emergency_cost_yuan+WEIGHT*table.fixed_cvar_yuan,atol=VALIDATION_TOL,rtol=0)
        np.testing.assert_allclose(table.J_roll_yuan,table.roll_adjustment_cost_yuan+table.roll_expected_emergency_cost_yuan+WEIGHT*table.roll_cvar_yuan,atol=VALIDATION_TOL,rtol=0)
        self.assertTrue(table.V_yuan.ge(-VALIDATION_TOL).all())
        self.assertTrue(table.reconstructed_J_roll_difference.le(VALIDATION_TOL).all())
        for column in ('fixed_primary_status','fixed_secondary_status','roll_primary_status','roll_secondary_status'):
            self.assertTrue(table[column].eq('optimal').all())
        self.assertTrue(table[['fixed_max_violation','roll_max_violation']].le(VALIDATION_TOL).all().all())
        # 从落盘明细再次核对正式SOC与每一轮合同，而非仅相信程序passed字段。
        actual = pd.read_csv(root/'outputs/q3/final/q3_actual_schedule.csv',float_precision='round_trip').set_index(['date','slot'])
        plans = pd.read_csv(root/'outputs/q3/final/q3_plan_updates.csv',float_precision='round_trip')
        daily_plans = dict(tuple(plans.groupby('date')))
        for row in table.itertuples():
            hour = int(row.update_time[:2])
            self.assertAlmostEqual(row.current_soc_kwh,float(actual.loc[(row.date,hour*6+1),'soc_real_start_kwh']),delta=VALIDATION_TOL)
            previous,current = previous_contract(daily_plans[row.date],hour)
            self.assertAlmostEqual(row.previous_contract_total_kwh,float(previous.sum()),delta=VALIDATION_TOL)
            self.assertAlmostEqual(row.J_roll_yuan,float(current.primary_objective.iloc[0]),delta=VALIDATION_TOL)
        validation = json.loads((folder/'q3_information_value_validation.json').read_text(encoding='utf-8'))
        self.assertTrue(validation['sha256_unchanged'])
        from src.common.data_loader import file_hash
        for name,digest in validation['sha256'].items():
            self.assertEqual(file_hash(root/name),digest,name)


if __name__=='__main__':
    unittest.main()
