import json
from pathlib import Path
import unittest
import pandas as pd
import importlib.util

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/17_plot_q2_q3_annual_comparison.py"
spec = importlib.util.spec_from_file_location("q2_q3_annual_comparison", SCRIPT)
comparison = importlib.util.module_from_spec(spec)
spec.loader.exec_module(comparison)

ROOT = Path(__file__).resolve().parents[1]


class AnnualComparisonTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.q2 = json.loads((ROOT/"outputs/q2/q2_metrics.json").read_text(encoding="utf-8"))
        cls.q3 = json.loads((ROOT/"outputs/q3/final/q3_annual_metrics.json").read_text(encoding="utf-8"))

    def test_source_and_four_metrics(self):
        table = comparison.build_table(self.q2, self.q3)
        self.assertEqual(len(table), 4)
        self.assertEqual(table.q2_relative_percent.tolist(), [100.0]*4)
        self.assertEqual(table.metric.iloc[3], "emergency_purchase_slot_count")
        self.assertEqual(table.q2_raw.iloc[3], self.q2["emergency_purchase_slot_count"])
        self.assertEqual(table.q3_raw.iloc[3], self.q3["emergency_slot_count"])

    def test_q3_parameters_and_raw_precision(self):
        table = comparison.build_table(self.q2, self.q3)
        row = table.iloc[0]
        expected = self.q3["total_actual_cost_yuan"] / self.q2["total_actual_cost_yuan"] * 100
        self.assertAlmostEqual(row.q3_relative_percent, expected, places=12)
        self.assertAlmostEqual(row.q3_vs_q2_change_percent, (expected-100), places=12)
        with self.assertRaises(ValueError):
            bad = dict(self.q3, alpha=.90)
            comparison.build_table(self.q2, bad)

    def test_outputs_generated_without_changing_sources(self):
        before_q2 = (ROOT/"outputs/q2/q2_metrics.json").read_bytes()
        before_q3 = (ROOT/"outputs/q3/final/q3_annual_metrics.json").read_bytes()
        table = comparison.main(ROOT)
        png = ROOT/"outputs/figures/q3/q2_q3_annual_relative_comparison.png"
        csv = ROOT/"outputs/figures/q3/q2_q3_annual_relative_comparison.csv"
        self.assertTrue(png.exists() and png.stat().st_size > 0)
        self.assertTrue(csv.exists())
        self.assertEqual(len(pd.read_csv(csv)), 4)
        self.assertEqual(before_q2, (ROOT/"outputs/q2/q2_metrics.json").read_bytes())
        self.assertEqual(before_q3, (ROOT/"outputs/q3/final/q3_annual_metrics.json").read_bytes())
        self.assertEqual(len(table), 4)
