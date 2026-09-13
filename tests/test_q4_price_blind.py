"""价格盲消融的信息边界、唯一处理变量和真实结算。"""

from pathlib import Path
import unittest

import numpy as np

from src.analysis.q4_price_blind import blind_forecast, run_blind_dates, validate_blind
from src.analysis.model_validation import frozen_hashes
from src.q3.annual import FORMAL_DATES
from src.q4 import annual
from src.q4.inputs import load_inputs
from src.q4.metrics import load_outputs
from src.q4.price_forecasting import PriceStream, forecast_price

ROOT = Path(__file__).resolve().parents[1]


class PriceBlindTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.before = frozen_hashes(ROOT)
        _, cls.prices, _ = load_inputs(ROOT)

    @classmethod
    def tearDownClass(cls):
        if cls.before != frozen_hashes(ROOT):
            raise AssertionError("冻结文件被修改")

    def test_only_causal_baseline_shape_removed(self):
        day = FORMAL_DATES[0]
        prior = {d:p for d,p in self.prices.items() if d<day}
        original, checked = forecast_price(prior, day)
        blind, diagnostic = blind_forecast(prior, day)
        np.testing.assert_array_equal(blind, np.full(144, original.mean()))
        self.assertGreater(np.ptp(original), 0.)
        self.assertEqual({k:diagnostic[k] for k in checked}, checked)
        changed = {**prior, day:np.full(144,99999.), FORMAL_DATES[1]:np.full(144,88888.)}
        np.testing.assert_array_equal(blind_forecast(changed, day)[0], blind)

    def test_revealed_prices_and_future_flatness(self):
        blind, _ = blind_forecast(self.prices, FORMAL_DATES[0])
        stream = PriceStream(blind)
        np.testing.assert_array_equal(np.asarray(stream), blind)
        real = self.prices[FORMAL_DATES[0]]
        for slot in range(1,41):
            stream.reveal(slot,float(real[slot-1]))
            view = np.asarray(stream)
            np.testing.assert_array_equal(view[:slot], real[:slot])
            np.testing.assert_array_equal(view[slot:], np.full(144-slot, stream.gamma*blind[0]))
        self.assertEqual(len(stream.observed),40)

    def test_original_model_history_and_settlement_dependencies_unchanged(self):
        self.assertEqual(run_blind_dates.__code__, annual.run_dates.__code__)
        for name in ("HistoricalCache", "run_three", "validate_outputs"):
            self.assertIs(run_blind_dates.__globals__[name], annual.run_dates.__globals__[name])
        self.assertIs(annual.run_dates.__globals__["forecast_price"], forecast_price)
        self.assertIs(run_blind_dates.__globals__["forecast_price"], blind_forecast)

    def test_saved_smoke_actual_settlement(self):
        folder = ROOT / "outputs/model_validation/q4_price_blind/smoke"
        if not (folder / "q4_metrics.json").exists():
            self.skipTest("价格盲首日尚未运行")
        outputs, _ = load_outputs(folder)
        checked = validate_blind(outputs,self.prices,formal=False)
        self.assertTrue(checked["passed"])
        self.assertEqual(checked["slots"],144)
        self.assertTrue(outputs["daily_metrics"].alpha.eq(.85).all())
        self.assertTrue(outputs["daily_metrics"]["lambda"].eq(.25).all())


if __name__ == "__main__":
    unittest.main()
