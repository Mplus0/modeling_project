"""合成边界错误的快照测试：不表示已复现用户真实失败组。"""
import json
from pathlib import Path
import tempfile
import unittest
import numpy as np
from src.q3.optimizer import solve_actual_step
from src.q4.q4_3 import save_negative_input


class FailureDiagnosticsTests(unittest.TestCase):
    def test_each_negative_input_captured_and_replayable(self):
        for name in ("load_forecast","pv_forecast","price","commitment"):
            arrays = {k:np.ones(144) for k in ("load_forecast","pv_forecast","price","commitment")}
            arrays[name][83] = -1e-10
            with tempfile.TemporaryDirectory() as tmp:
                try:
                    solve_actual_step(37,1.,1.,**arrays,current_soc=6000.,plan_terminal_soc=6000.,date="2025-03-20")
                except ValueError as error:
                    report = save_negative_input(error,.8,0.,6000.,tmp)
                else:
                    self.fail("诊断阶段不得更改原非负检查")
                self.assertEqual(report["slot"],37)
                self.assertEqual(report["date"],"2025-03-20")
                self.assertEqual(report["inputs"][name]["minimum"],-1e-10)
                self.assertEqual(report["inputs"][name]["negative_count"],1)
                self.assertEqual(len(report["inputs"]),4)
                with np.load(Path(tmp)/"last_negative_input.npz") as data:
                    kwargs = {k:data[k].item() if data[k].ndim==0 else data[k] for k in data.files}
                    with self.assertRaisesRegex(ValueError,"必须非负"):
                        solve_actual_step(**kwargs)
                self.assertEqual(json.loads((Path(tmp)/"last_negative_input.json").read_text(encoding="utf-8")),report)
