"""价格公共回测、因果边界和逐步刷新测试。"""
from datetime import date,timedelta
import unittest
import numpy as np
from src.q2.forecasting import candidate_prediction, nmae
from src.q4.price_forecasting import PRICE_WINDOWS, PRICE_EPSILON, forecast_price, PriceStream


class PriceTests(unittest.TestCase):
    def setUp(self):
        self.start = date(2025,1,1)
        self.history = {self.start+timedelta(days=i):np.full(144,1.+i/100) for i in range(70)}
        self.day = self.start+timedelta(days=50)

    def test_public_dates_stride_nmae_and_candidates(self):
        baseline,diagnostic = forecast_price(self.history,self.day)
        self.assertEqual(PRICE_WINDOWS,(1,2,3,4))
        eligible = [self.start+timedelta(days=i) for i in range(28,50)]
        self.assertEqual(diagnostic["price_backtest_dates"],"|".join(map(str,eligible)))
        nested = {d:{"load":v} for d,v in self.history.items()}
        for w in PRICE_WINDOWS:
            real = np.concatenate([self.history[d] for d in eligible])
            predicted = np.concatenate([candidate_prediction(nested,d,"load",w) for d in eligible])
            self.assertAlmostEqual(diagnostic[f"price_nmae_w{w}"],nmae(real,predicted))
        chosen = diagnostic["chosen_price_window_weeks"]
        np.testing.assert_array_equal(baseline,np.mean([self.history[self.day-timedelta(days=7*i)] for i in range(1,chosen+1)],axis=0))

    def test_target_and_future_cannot_change_selection(self):
        original = forecast_price(self.history,self.day)
        changed = {d:(v*100 if d>=self.day else v) for d,v in self.history.items()}
        updated = forecast_price(changed,self.day)
        np.testing.assert_array_equal(original[0],updated[0])
        self.assertEqual(original[1],updated[1])

    def test_tie_selects_smaller_and_insufficient_stops(self):
        constant = {d:np.ones(144) for d in self.history}
        self.assertEqual(forecast_price(constant,self.day)[1]["chosen_price_window_weeks"],1)
        with self.assertRaises(ValueError):
            forecast_price(constant,self.start+timedelta(days=27))

    def test_window_is_selected_again_each_day(self):
        rng = np.random.default_rng(37)
        history = {self.start+timedelta(days=i):np.full(144,rng.uniform(.1,4.)) for i in range(100)}
        windows = [forecast_price(history,self.start+timedelta(days=i))[1]["chosen_price_window_weeks"] for i in range(32,100)]
        self.assertGreater(len(set(windows)),1)

    def test_gamma_and_contract_boundary(self):
        stream = PriceStream(np.full(144,2.))
        self.assertEqual(stream.gamma,1.)
        for slot in range(1,37):
            stream.reveal(slot,3.)
        before_contract = np.asarray(stream).copy()
        self.assertAlmostEqual(before_contract[36],3.,places=10)
        stream.reveal(37,6.)
        self.assertAlmostEqual(stream.gamma,(36*3+6)/(37*2+PRICE_EPSILON))
        self.assertEqual(stream[36],6.)
        np.testing.assert_allclose(stream[37:],stream.gamma*2,rtol=0,atol=0)
        np.testing.assert_array_equal(before_contract[:36],np.full(36,3.))
        self.assertEqual(len(stream.refreshes),37)
        self.assertTrue(np.isfinite(stream).all())
        with self.assertRaises(ValueError):
            stream.reveal(39,1.)

    def test_epsilon_numerical_only_and_nonnegative(self):
        stream = PriceStream(np.ones(144))
        stream.reveal(1,1.)
        self.assertLess(abs(stream.gamma-1.),2e-12)
        zero = PriceStream(np.zeros(144))
        zero.reveal(1,0.)
        self.assertTrue(np.isfinite(zero).all())
        self.assertTrue((np.asarray(zero)>=0).all())
        for invalid in (np.full(144,-1.),np.full(144,np.nan)):
            with self.assertRaises(ValueError):
                PriceStream(invalid)
