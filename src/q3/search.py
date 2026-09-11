"""后续全年联合搜索的候选集合与统一评分；不自动启动全年仿真。"""

import numpy as np
import pandas as pd

from src.q3.parameters import PARAMETER_GRID
from src.q3.optimizer import VALIDATION_TOL


def score_annual_results(daily_results, tolerance=VALIDATION_TOL):
    """接收20组完整逐日实际结果，返回评分表及全部并列最优参数。"""
    required = ["alpha", "lambda", "date", "total_actual_cost_yuan", "emergency_slot_count"]
    if not set(required).issubset(daily_results.columns):
        raise ValueError("Q3全年评分缺少必要逐日实际指标")
    if not np.isfinite(tolerance) or tolerance <= 0:
        raise ValueError("Q3评分数值容差必须为有限正数")
    data = daily_results[required].copy()
    data["date"] = pd.to_datetime(data["date"], errors="raise")
    numeric = data[[c for c in required if c != "date"]].to_numpy(float)
    if data.isna().any().any() or not np.isfinite(numeric).all():
        raise ValueError("Q3全年评分含缺失或非有限值")
    if set(zip(data.alpha, data["lambda"])) != set(PARAMETER_GRID):
        raise ValueError("Q3必须汇齐全部20组合法参数结果才能统一评分")
    counts = data.emergency_slot_count.to_numpy(float)
    if ((counts < 0) | (counts > 144) | (counts != np.floor(counts))).any():
        raise ValueError("Q3每日有效紧急购电时段数必须为0至144的整数")
    expected_dates = pd.date_range("2025-02-01", "2025-12-31", freq="D")
    rows = []
    for (alpha, weight), group in data.groupby(["alpha", "lambda"], sort=True):
        if not pd.DatetimeIndex(group.date.sort_values()).equals(expected_dates):
            raise ValueError(f"Q3参数({alpha}, {weight})必须具有相同的334个完整日期，不允许缺日或重复")
        costs = group.total_actual_cost_yuan.to_numpy(float)
        # 只汇总已结算实际费用，日费用波动使用334天总体标准差。
        rows.append(dict(alpha=alpha, **{"lambda": weight}, total_cost=float(costs.sum()),
                         emergency_slot_count=int(group.emergency_slot_count.sum()),
                         daily_cost_std=float(np.std(costs, ddof=0))))
    result = pd.DataFrame(rows)
    result["Score"] = 0.
    for column, weight in (("total_cost", .5), ("emergency_slot_count", .3), ("daily_cost_std", .2)):
        low, high = float(result[column].min()), float(result[column].max())
        # 三个指标各自使用全部20组的共同上下界；近常量指标统一记0。
        normalized = np.zeros(len(result)) if high-low <= tolerance else (result[column]-low)/(high-low)
        result[f"normalized_{column}"] = normalized
        result[f"min_{column}"] = low
        result[f"max_{column}"] = high
        result["Score"] += weight*normalized
    # 不擅自添加并列时的偏好；精确argmin并列结果全部返回供团队选择。
    winners = result.loc[result.Score.eq(result.Score.min()), ["alpha", "lambda"]].reset_index(drop=True)
    return result, winners
