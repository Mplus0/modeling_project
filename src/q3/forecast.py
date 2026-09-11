"""复用Q2负荷预测，将合法发布的整点光伏预测转换为十分钟电量。"""

import numpy as np
import pandas as pd

from src.q2.forecasting import forecast_day

UPDATE_HOURS = (0, 6, 12, 18)


def load_hourly_forecasts(path):
    frame = pd.read_csv(path, float_precision="round_trip")
    expected = ["issue_datetime", "target_datetime", "horizon_hour", "pv_forecast_kw"]
    if list(frame.columns) != expected:
        raise ValueError("Q3整点光伏预测列名不符")
    for column in ("issue_datetime", "target_datetime"):
        frame[column] = pd.to_datetime(frame[column], errors="raise")
    if frame.isna().any().any() or not np.isfinite(frame.pv_forecast_kw.to_numpy(float)).all():
        raise ValueError("Q3整点预测含缺失或非有限值")
    expected_issues = pd.date_range("2025-01-01", periods=1460, freq="6h")
    issues = {}
    for issue, group in frame.groupby("issue_datetime", sort=True):
        group = group.sort_values("horizon_hour").reset_index(drop=True)
        if group.horizon_hour.tolist() != list(range(1, 25)):
            raise ValueError(f"{issue}必须包含未来1至24小时预测各一条")
        expected_targets = pd.date_range(issue + pd.Timedelta(hours=1), periods=24, freq="h")
        if not pd.DatetimeIndex(group.target_datetime).equals(expected_targets):
            raise ValueError(f"{issue}的发布时间、预测时效和目标时刻不一致")
        issues[issue] = group
    if not pd.DatetimeIndex(issues).equals(expected_issues):
        raise ValueError("Q3需要2025年每日00/06/12/18点共1460次发布")
    return issues


def interpolate_issue(issue_table, issue_time, current_actual_pv_kw, targets):
    """接口只接收发布时刻的当前实测标量，不接收未来真实光伏。"""
    issue = pd.Timestamp(issue_time)
    targets = pd.DatetimeIndex(targets)
    if not issue_table.issue_datetime.eq(issue).all():
        raise ValueError("不能使用其他发布时间或未来版本的光伏预测")
    expected = pd.date_range(issue + pd.Timedelta(hours=1), periods=24, freq="h")
    table = issue_table.sort_values("horizon_hour")
    if table.horizon_hour.tolist() != list(range(1, 25)) or not pd.DatetimeIndex(table.target_datetime).equals(expected):
        raise ValueError("整点目标与发布时效不一致")
    if len(targets) == 0 or (targets <= issue).any() or (targets > expected[-1]).any():
        raise ValueError("只允许插值发布后且处于本版24小时覆盖范围内的目标")
    minutes = (targets - issue).total_seconds().to_numpy() / 60
    if not np.isin(minutes, np.arange(10, 1441, 10)).all():
        raise ValueError("目标必须位于发布后的十分钟网格")
    endpoints = np.r_[float(current_actual_pv_kw), table.pv_forecast_kw.to_numpy(float)]
    if not np.isfinite(endpoints).all() or (endpoints < 0).any():
        raise ValueError("光伏插值端点必须为有限非负功率")
    # 首小时左端为当前实测、右端为新版本下一整点预测；后续整点之间线性插值。
    power = np.interp(minutes, np.arange(25) * 60, endpoints)
    return power * (10 / 60)


def load_prediction(history, target, cache=None):
    # 直接调用Q2已确认的公共回测日和动态选窗逻辑，仅取其负荷预测结果。
    forecasts, diagnostics = forecast_day(history, target, cache)
    return forecasts["load"].copy(), diagnostics


def fuse_remaining(previous, new_remaining, first_slot, rho):
    previous, new_remaining = np.asarray(previous, float), np.asarray(new_remaining, float)
    if not 0 <= rho <= 1 or not 1 <= first_slot <= len(previous):
        raise ValueError("融合可信度或起始slot不符")
    start = first_slot - 1
    if new_remaining.shape != previous[start:].shape:
        raise ValueError("融合仅允许更新剩余时域")
    result = previous.copy()
    result[start:] = (1-rho)*previous[start:] + rho*new_remaining
    return result
