"""已确认的价格盲消融：只移除0:00因果预测的日内形状。"""

import numpy as np
import pandas as pd

from src.analysis.ablation_adapters import bind
from src.q4 import annual
from src.q4.price_forecasting import forecast_price
from src.q4.validation import validate_outputs

STEM = "q4_price_blind"
TREATMENT = "目标日0:00因果预测曲线的均值；日内保留原因果gamma，未来预测无时序形状；按真实动态价格结算"


def blind_forecast(history, target, cache=None):
    prediction, diagnostic = forecast_price(history, target, cache)
    # 均值仅取合法历史得到的c0，不读取目标日真实价格；原选窗完全保留。
    mean = float(prediction.mean())
    return np.full(prediction.shape, mean), {**diagnostic, "price_information_treatment": TREATMENT,
                                            "causal_baseline_mean": mean}


# 只替换价格预测的返回曲线；原Q4/Q3日循环、历史残差和真实结算不变。
run_blind_dates = bind(annual.run_dates, forecast_price=blind_forecast)


def validate_blind(outputs, prices, formal):
    checked = validate_outputs(outputs, 3, formal=formal)
    cache = {}
    for row in outputs["daily_metrics"].itertuples():
        day = pd.Timestamp(row.date).date()
        original, _ = forecast_price({d: p for d, p in prices.items() if d < day}, day, cache)
        refresh = outputs["price_refresh"].loc[lambda f: f.date.eq(row.date)]
        baseline = refresh.baseline_price_yuan_per_kwh.to_numpy(float)
        # 从严格历史重新计算均值；不得用目标日真均价替代。
        np.testing.assert_array_equal(baseline, np.full(144, original.mean()))
        actual = outputs["actual_schedule"].loc[lambda f: f.date.eq(row.date)]
        np.testing.assert_array_equal(actual.price_yuan_per_kwh.to_numpy(), prices[day])
    return {**checked, "causal_mean_verified": True, "future_price_shape_removed": True,
            "real_price_settlement_verified": True, "treatment": TREATMENT}


def run_experiment(root, smoke=False):
    # 用户已终止本实验；拒绝入口，且不触碰任何原始失败记录。
    raise RuntimeError("Q4-A模型检验已终止，不再运行；原attempt.json及审计记录保留")
