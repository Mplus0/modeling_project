"""同星期公共历史回测选窗，以及仅持有已揭示价格的日内适配器。"""

from datetime import timedelta
import numpy as np
from src.q2.forecasting import candidate_prediction, select_window

PRICE_WINDOWS = (1, 2, 3, 4)
PRICE_EPSILON = 1e-12  # 仅防止零分母，不参与选窗或参数搜索。


def forecast_price(history, target, cache=None):
    prior = {d:{"load":np.asarray(v,float)} for d,v in history.items() if d<target}
    eligible = [d for d in sorted(prior) if all(d-timedelta(days=7*k) in prior for k in range(1,5))]
    if not eligible:
        raise ValueError("电价选窗缺少四候选公共历史回测日期")
    cache = {} if cache is None else cache
    errors, denominator = np.zeros(4), 0.
    for day in eligible:
        if day not in cache:
            real = prior[day]["load"]
            if real.shape!=(144,) or not np.isfinite(real).all() or (real<0).any():
                raise ValueError("历史价格必须为144个非负有限值")
            cache[day] = (np.array([np.abs(real-candidate_prediction(prior,day,"load",w)).sum()
                                   for w in PRICE_WINDOWS]),float(real.sum()))
        error,total = cache[day]
        errors += error
        denominator += total
    if denominator<=0:
        raise ValueError("价格历史回测NMAE分母必须为正，未自动修复")
    scores = dict(zip(PRICE_WINDOWS,map(float,errors/denominator)))
    chosen = select_window(scores)
    prediction = candidate_prediction(prior,target,"load",chosen)
    if prediction.shape!=(144,) or not np.isfinite(prediction).all() or (prediction<0).any():
        raise ValueError("价格预测必须为144个非负有限值")
    diagnostics = dict(date=str(target),chosen_price_window_weeks=chosen,price_backtest_days=len(eligible),
                       price_backtest_first=str(eligible[0]),price_backtest_last=str(eligible[-1]),
                       price_backtest_dates="|".join(map(str,eligible)))
    diagnostics.update({f"price_nmae_w{w}":s for w,s in scores.items()})
    return prediction,diagnostics


class PriceStream:
    """数组协议适配冻结Q3：合同先读取预测，观测回调随后揭示当前价格。"""
    def __init__(self, baseline):
        self.baseline = np.asarray(baseline,float).copy()
        if self.baseline.shape!=(144,) or not np.isfinite(self.baseline).all() or (self.baseline<0).any():
            raise ValueError("0:00价格预测尺寸或数值不符")
        self.observed = []
        self.refreshes = []

    @property
    def gamma(self):
        n = len(self.observed)
        return float(sum(self.observed)/(self.baseline[:n].sum()+PRICE_EPSILON)) if n else 1.

    def reveal(self, slot, value):
        if slot!=len(self.observed)+1 or not np.isfinite(value) or value<0:
            raise ValueError("价格必须按slot顺序逐项揭示非负有限观测")
        self.observed.append(float(value))
        self.refreshes.append(dict(slot=slot,gamma=self.gamma,observed_count=slot,
                                    observed_price_sum=float(sum(self.observed)),
                                    baseline_observed_sum=float(self.baseline[:slot].sum())))

    def __len__(self):
        return 144

    def __array__(self, dtype=None, copy=None):
        # 当前已揭示项用真实价格，未来只用gamma*c0；对象不持有未来真实价格。
        values = self.gamma*self.baseline
        values[:len(self.observed)] = self.observed
        if not np.isfinite(values).all():
            raise ValueError("日内价格预测出现非有限值")
        return np.array(values,dtype=dtype,copy=True)

    def __getitem__(self, key):
        return np.asarray(self)[key]
