"""论文只用已验收全年结果，Q4-A退出且原审计记录不变。"""

import json
from pathlib import Path
import unittest
from unittest.mock import patch

import pandas as pd

from src.common.data_loader import file_hash
from src.analysis.paper_validation import write_paper_outputs
from src.analysis.q4_price_blind import run_experiment

ROOT = Path(__file__).resolve().parents[1]


class PaperValidationTests(unittest.TestCase):
    def test_q4_entry_disabled_without_writes(self):
        marker = ROOT / "outputs/model_validation/q4_price_blind/run/attempt.json"
        before = file_hash(marker)
        with patch("src.analysis.q4_price_blind.run_blind_dates", side_effect=AssertionError("不得运行")):
            for smoke in (False, True):
                with self.assertRaisesRegex(RuntimeError, "已终止"):
                    run_experiment(ROOT, smoke)
        self.assertEqual(file_hash(marker), before)

    def test_paper_exclusion_and_audit_unchanged(self):
        base = ROOT / "outputs/model_validation"
        files = [base / "q4_price_blind" / name for name in
                 ("run/attempt.json", "q4_price_blind.json", "q4_price_blind_validation.json")]
        before = {p:file_hash(p) for p in files}
        checked = write_paper_outputs(ROOT)
        self.assertEqual(before, {p:file_hash(p) for p in files})
        table = pd.read_csv(base / "summary/paper_ablation_comparison.csv")
        self.assertFalse(table.experiment.eq("Q4").any())
        self.assertTrue(checked["Q3"]["passed"])
        if not checked["Q2"]["passed"]:
            self.assertFalse(table.experiment.eq("Q2").any())
        paper = (base / "summary/model_validation_paper_summary.md").read_text(encoding="utf-8")
        self.assertNotIn("SCIP", paper)
        self.assertNotIn("solver numerical failure", paper)

    def test_rate_direction_and_no_soc_improvement(self):
        base = ROOT / "outputs/model_validation/summary"
        if not (base / "paper_ablation_comparison.csv").exists():
            write_paper_outputs(ROOT)
        table = pd.read_csv(base / "paper_ablation_comparison.csv").set_index("metric")
        self.assertGreater(table.loc["total_actual_cost_yuan", "reduction_percent"], 0)
        self.assertLess(table.loc["emergency_purchase_kwh", "reduction_percent"], 0)
        self.assertTrue(pd.isna(table.loc["final_soc_kwh", "reduction_percent"]))
        self.assertTrue(pd.isna(table.loc["simultaneous_slots", "reduction_percent"]))
