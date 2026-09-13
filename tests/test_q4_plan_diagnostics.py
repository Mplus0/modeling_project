"""故障记录器的合成注入测试，不代表复现本次真实SCIP故障。"""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
from pyscipopt import Model
from src.q3.optimizer import solve_plan, VALIDATION_TOL
from src.q4.plan_diagnostics import diagnostic_plan, replay_snapshot


class PlanDiagnosticsTests(unittest.TestCase):
    def test_success_is_identical_and_writes_nothing(self):
        args = (np.full((2,36),100.),np.full((2,36),20.),np.full(36,.7),6000.,.85,.25,np.full(36,60.))
        original = solve_plan(*args)
        with tempfile.TemporaryDirectory() as tmp:
            observed = diagnostic_plan(*args,date='2025-05-22',directory=tmp)
            self.assertEqual(list(Path(tmp).iterdir()),[])
        for key in ('primary_star','primary_objective','secondary_throughput','grid','increase','decrease','scenario_terminal_soc'):
            np.testing.assert_allclose(observed[key],original[key],atol=VALIDATION_TOL,rtol=0)

    def test_secondary_failure_captures_primary_and_exact_inputs(self):
        class InjectedFailure(Model):
            def optimize(self):
                self.calls = getattr(self,'calls',0)+1
                if self.calls==2:
                    raise Exception('TEST ONLY: injected secondary LP error')
                return super().optimize()
        args = (np.full((2,36),100.),np.full((2,36),20.),np.full(36,.7),6000.,.90,.25,np.full(36,60.))
        with tempfile.TemporaryDirectory() as tmp:
            with patch('src.q4.plan_diagnostics.Model',InjectedFailure):
                with self.assertRaisesRegex(Exception,'TEST ONLY'):
                    diagnostic_plan(*args,date='2025-05-22',directory=tmp)
            report_path, = Path(tmp).glob('*.json')
            report = json.loads(report_path.read_text(encoding='utf-8'))
            self.assertEqual(report['failed_stage'],'secondary')
            self.assertEqual(report['primary_status'],'optimal')
            self.assertEqual(report['optimize_calls'],2)
            self.assertIsNotNone(report['primary_star'])
            self.assertEqual((report['horizon_length'],report['scenario_count'],report['slot'],report['update_time']),(36,2,109,'18:00'))
            self.assertIn('primary_xi_range',report)
            with np.load(report_path.with_suffix('.npz')) as saved:
                for key,values in zip(('load_scenarios','pv_scenarios','price','start_soc','alpha','risk_weight','previous_plan'),args):
                    np.testing.assert_array_equal(saved[key],values)
            # 撤销合成注入后只求同一个LP；不调用日循环，证明NPZ足够重建。
            results = replay_snapshot(report_path.with_suffix('.npz'))
            self.assertTrue(results[0]['success'])
            self.assertEqual(results[0]['secondary_status'],'optimal')

    def test_primary_failure_and_absent_previous_contract(self):
        class InjectedFailure(Model):
            def optimize(self):
                raise Exception('TEST ONLY: injected primary error')
        with tempfile.TemporaryDirectory() as tmp:
            with patch('src.q4.plan_diagnostics.Model',InjectedFailure):
                with self.assertRaisesRegex(Exception,'TEST ONLY'):
                    diagnostic_plan(np.ones((1,144)),np.zeros((1,144)),np.ones(144),6000.,.9,.25,
                                    date='2025-05-22',directory=tmp)
            path, = Path(tmp).glob('*.json')
            report = json.loads(path.read_text(encoding='utf-8'))
            self.assertEqual(report['failed_stage'],'primary')
            self.assertIsNone(report['primary_star'])
            self.assertIsNone(report['input_ranges']['previous_plan'])
            npz = path.with_suffix('.npz')
            with np.load(npz) as saved:
                self.assertFalse(bool(saved['previous_plan_present']))
            npz.write_bytes(b'corrupt test fixture')
            with self.assertRaisesRegex(ValueError,'SHA'):
                replay_snapshot(npz)
