"""只使用目标日之前的已实现数据，动态选择同星期负荷和连续日光伏窗口。"""

from datetime import timedelta

import numpy as np
import pandas as pd

from src.common.time_utils import clock_seconds

M_LOAD = (1, 2, 3, 4)
K_PV = (3, 5, 7, 14)
FORMAL_DATES = pd.date_range("2025-02-01", "2025-12-31").date.tolist()
TIE_TOLERANCE = 1e-12


def nmae(actual, predicted):
    actual, predicted = np.asarray(actual, float), np.asarray(predicted, float)
    if actual.shape != predicted.shape or not np.isfinite(actual).all() or not np.isfinite(predicted).all():
        raise ValueError("NMAE 输入尺寸或有限性不符")
    denominator = float(actual.sum())
    if denominator <= 0:
        raise ValueError("NMAE 实际值总和必须大于零")
    return float(np.abs(actual - predicted).sum() / denominator)


def select_window(scores):
    best = min(scores.values())
    # 同精度最优时选择较小窗口，避免字典遍历或求和误差影响复现。
    return min(window for window, score in scores.items() if abs(score - best) <= TIE_TOLERANCE)


def candidate_prediction(history, target, kind, window):
    stride = 7 if kind == "load" else 1
    required = [target - timedelta(days=stride * k) for k in range(1, window + 1)]
    if any(day >= target or day not in history for day in required):
        raise ValueError(f"{target} 的 {kind} 窗口缺少严格历史观测")
    return np.mean([history[day][kind] for day in required], axis=0)


def forecast_day(history, target, cache=None):
    if not history or any(day >= target for day in history):
        raise ValueError("预测历史为空或包含目标日/未来信息")
    cache = {} if cache is None else cache
    forecasts, diagnostics = {}, {"date": target.isoformat()}
    for kind, windows, stride in [("load", M_LOAD, 7), ("pv", K_PV, 1)]:
        # 四个候选使用相同的全部可用回测日，且每个回测预测只能读取该日之前。
        eligible = [day for day in sorted(history)
                    if all(day - timedelta(days=stride * k) in history for k in range(1, max(windows) + 1))]
        if not eligible:
            raise ValueError(f"{target} 的 {kind} 尚无公共回测日期")
        totals = np.zeros(len(windows))
        denominator = 0.0
        for day in eligible:
            key = (kind, day)
            if key not in cache:
                actual = history[day][kind]
                cache[key] = (np.array([np.abs(actual - candidate_prediction(history, day, kind, w)).sum()
                                        for w in windows]), float(actual.sum()))
            errors, actual_sum = cache[key]
            totals += errors
            denominator += actual_sum
        if denominator <= 0:
            raise ValueError(f"{kind} 回测 NMAE 分母不为正")
        scores = {w: float(totals[i] / denominator) for i, w in enumerate(windows)}
        chosen = select_window(scores)
        forecasts[kind] = candidate_prediction(history, target, kind, chosen)
        suffix = "weeks" if kind == "load" else "days"
        prefix = "m" if kind == "load" else "k"
        diagnostics[f"{kind}_window_{suffix}"] = chosen
        diagnostics.update({f"{kind}_nmae_{prefix}{w}": score for w, score in scores.items()})
        diagnostics[f"{kind}_backtest_days"] = len(eligible)
        diagnostics[f"{kind}_backtest_first"] = eligible[0].isoformat()
        diagnostics[f"{kind}_backtest_last"] = eligible[-1].isoformat()
        diagnostics[f"{kind}_backtest_dates"] = "|".join(day.isoformat() for day in eligible)
    return forecasts, diagnostics


def load_daily_inputs(history_path, price_path):
    frame = pd.read_csv(history_path, float_precision="round_trip")
    price_frame = pd.read_csv(price_path, float_precision="round_trip")
    if len(frame) != 52560 or price_frame.slot.tolist() != list(range(1, 145)):
        raise ValueError("Q2 历史记录或固定电价 slot 数量不符")
    price = price_frame.price_yuan_per_kwh.to_numpy(float)
    if not np.isfinite(price).all():
        raise ValueError("固定电价包含非有限数值")
    expected = pd.date_range("2025-01-01", "2025-12-31").date.tolist()
    days = {}
    for label, group in frame.groupby("source_date", sort=False):
        day = pd.Timestamp(label).date()
        if len(group) != 144 or [clock_seconds(v) for v in group.source_time] != list(range(600, 86401, 600)):
            raise ValueError(f"{day} 的 144 个时间点不完整或顺序不符")
        load, pv = group.load_kwh.to_numpy(float), group.pv_actual_kwh.to_numpy(float)
        if not np.isfinite(np.r_[load, pv]).all():
            raise ValueError(f"{day} 的能量包含缺失或非有限值")
        days[day] = {"load": load, "pv": pv, "source_time": group.source_time.to_numpy(copy=True)}
    if list(days) != expected:
        raise ValueError("历史日期须为连续的2025年365天")
    return days, price
