"""验证论文绘图数据口径、输出格式和冻结结果完整性。"""

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import numpy as np
import pandas as pd

from src.common.data_loader import file_hash
from src.q1.plotting import TICKS, TICK_LABELS, plot_q1, prepare_plot_data

ROOT = Path(__file__).resolve().parents[1]
SOURCES = [ROOT / "data/processed/q1_input.csv", ROOT / "outputs/schedule/q1_schedule.csv",
           ROOT / "outputs/metrics/q1_metrics.json"]


class Q1PlottingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.inputs = pd.read_csv(SOURCES[0], float_precision="round_trip")
        cls.schedule = pd.read_csv(SOURCES[1], float_precision="round_trip")
        cls.metrics = json.loads(SOURCES[2].read_text(encoding="utf-8"))

    def test_energy_series_and_existing_columns(self):
        original = self.schedule.copy(deep=True)
        data = prepare_plot_data(self.inputs, self.schedule, self.metrics)
        self.assertEqual(data["slot"].tolist(), list(range(1, 145)))
        np.testing.assert_allclose(data["grid_purchase_kwh"], self.schedule.x_kwh + self.schedule.y_kwh, atol=1e-6, rtol=0)
        np.testing.assert_allclose(data["charge_input_kwh"], self.schedule.x_kwh + self.schedule.q_kwh, atol=1e-6, rtol=0)
        np.testing.assert_array_equal(data["charge_input_kwh"], self.schedule.charge_input_kwh)
        np.testing.assert_array_equal(data["z_kwh"], self.schedule.z_kwh)
        np.testing.assert_array_equal(data["load_kw"], self.inputs.load_kw)
        pd.testing.assert_frame_equal(original, self.schedule)

    def test_soc_and_time_positions(self):
        data = prepare_plot_data(self.inputs, self.schedule, self.metrics)
        self.assertEqual(len(data["states"]), 145)
        np.testing.assert_allclose(data["states"][[0, -1]], [6000, 6000], rtol=0, atol=1e-6)
        np.testing.assert_array_equal(data["states"][1:], self.schedule.soc_kwh)
        np.testing.assert_array_equal(data["state_positions"], np.arange(145))
        np.testing.assert_array_equal(TICKS, [0, 24, 48, 72, 96, 120, 144])
        self.assertEqual(TICK_LABELS, ["0:00", "4:00", "8:00", "12:00", "16:00", "20:00", "24:00"])
        np.testing.assert_array_equal(data["interval_positions"], np.arange(144) + 0.5)

    def test_bad_data_rejected(self):
        for column, value in [("grid_purchase_kwh", -100), ("charge_input_kwh", 10000),
                              ("soc_previous_kwh", 5999), ("soc_kwh", 11000),
                              ("load_kw", np.inf), ("z_kwh", np.nan), ("slot", 2)]:
            with self.subTest(column=column):
                bad = self.schedule.copy(deep=True)
                bad.loc[0, column] = value
                with self.assertRaises(ValueError):
                    prepare_plot_data(self.inputs, bad, self.metrics)
        with self.assertRaisesRegex(ValueError, "144"):
            prepare_plot_data(self.inputs, self.schedule.iloc[:-1], self.metrics)
        bad = self.schedule.copy(deep=True)
        bad.loc[143, "soc_kwh"] = 5999
        with self.assertRaisesRegex(ValueError, "初末"):
            prepare_plot_data(self.inputs, bad, self.metrics)

    def test_positions_do_not_parse_source_time(self):
        changed = self.schedule.assign(source_time="仅用于标签测试")
        data = prepare_plot_data(self.inputs, changed, self.metrics)
        np.testing.assert_array_equal(data["interval_positions"], np.arange(144) + 0.5)

    def test_outputs_and_frozen_hashes(self):
        frozen = SOURCES + [ROOT / "outputs/submissions/result1.xlsx"]
        before = {p: file_hash(p) for p in frozen}
        with TemporaryDirectory() as directory:
            paths = plot_q1(*SOURCES, directory)
            self.assertEqual(len(paths), 10)
            for path in paths:
                content = path.read_bytes()
                self.assertGreater(len(content), 1000)
                self.assertTrue(content.startswith(b"\x89PNG\r\n\x1a\n" if path.suffix == ".png" else b"%PDF-"))
            self.assertTrue((Path(directory) / "README.md").is_file())
        self.assertEqual(before, {p: file_hash(p) for p in frozen})


if __name__ == "__main__":
    unittest.main()
