"""手算分母口径、完整性拒绝、图表输出及冻结文件检查。"""

import importlib.util
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import numpy as np
import pandas as pd

from src.common.data_loader import file_hash
from src.q2.lag_similarity import compute_lag_similarity, load_and_validate_historical_power

ROOT = Path(__file__).resolve().parents[1]


class LagSimilarityTests(unittest.TestCase):
    def test_hand_calculated_valid_day_denominators(self):
        result = compute_lag_similarity([[1, 2], [2, 4], [4, 8]], [[2, 0], [1, 1], [0, 4]], max_lag=2)
        np.testing.assert_allclose(result.load_nmae, [9/18, 9/12])
        np.testing.assert_allclose(result.pv_nmae, [6/6, 6/4])
        self.assertEqual(result.lag_days.tolist(), [1, 2])
        with self.assertRaisesRegex(ValueError, "不为正"):
            compute_lag_similarity(np.ones((3, 2)), np.zeros((3, 2)), 2)

    def test_calendar_completeness_and_rollover(self):
        source = ROOT / "data/processed/historical_power.csv"
        frame = load_and_validate_historical_power(source)
        self.assertEqual(len(frame), 52560)
        self.assertEqual(str(frame.datetime.iloc[-1]), "2026-01-01 00:00:00")
        with TemporaryDirectory() as directory:
            bad = Path(directory) / "bad.csv"
            frame.iloc[:-1].to_csv(bad, index=False)
            with self.assertRaisesRegex(ValueError, "365天"):
                load_and_validate_historical_power(bad)
            duplicated = frame.copy()
            duplicated.iloc[1] = duplicated.iloc[0]
            duplicated.to_csv(bad, index=False)
            with self.assertRaisesRegex(ValueError, "不完整或重复"):
                load_and_validate_historical_power(bad)

    def test_entrypoint_outputs_and_protected_hashes(self):
        paths = list((ROOT / "data/processed").glob("*.csv")) + list((ROOT / "outputs/q2").glob("*"))
        paths += list((ROOT / "outputs/submissions").glob("*.xlsx"))
        paths += [ROOT / "outputs/schedule/q1_schedule.csv", ROOT / "outputs/metrics/q1_metrics.json"]
        before = {p: file_hash(p) for p in paths if p.is_file()}
        spec = importlib.util.spec_from_file_location("lag_entry", ROOT / "scripts/06_plot_q2_lag_similarity.py")
        entry = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(entry)
        self.assertEqual(entry.main(), 0)
        result = pd.read_csv(ROOT / "outputs/metrics/q2/q2_lag_similarity.csv")
        self.assertEqual(list(result.columns), ["lag_days", "load_nmae", "pv_nmae"])
        self.assertEqual(result.lag_days.tolist(), list(range(1, 15)))
        self.assertFalse(result.isna().any().any())
        for suffix in ("png", "pdf"):
            self.assertGreater((ROOT / f"outputs/figures/q2/q2_lag_similarity.{suffix}").stat().st_size, 1000)
        self.assertEqual(before, {p: file_hash(p) for p in before})
