"""仅用冻结历史数据描述日滞后相似性，不涉及预测训练或优化。"""

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
from matplotlib import font_manager, pyplot as plt
import numpy as np
import pandas as pd

from src.common.time_utils import clock_seconds


def load_and_validate_historical_power(path):
    frame = pd.read_csv(path, float_precision="round_trip")
    required = {"datetime", "source_date", "source_time", "load_kwh", "pv_actual_kwh"}
    if not required.issubset(frame.columns):
        raise ValueError("历史数据缺少日期、源时刻或实际电量列")
    dates = pd.to_datetime(frame.source_date, errors="raise")
    # 源日期决定日曲线归属；12月31日的末点虽落在次年午夜，仍属于该日。
    frame = frame.loc[dates.dt.year.eq(2025)].copy()
    frame["source_date"] = dates.loc[frame.index]
    frame["datetime"] = pd.to_datetime(frame["datetime"], errors="raise")
    frame = frame.sort_values("datetime").reset_index(drop=True)
    days = pd.date_range("2025-01-01", "2025-12-31")
    if len(frame) != 365 * 144 or not pd.Index(frame.source_date.drop_duplicates()).equals(days):
        raise ValueError("2025年历史数据必须包含连续365天，每天144条记录")
    for day, group in frame.groupby("source_date", sort=False):
        seconds = [clock_seconds(label) for label in group.source_time]
        if len(group) != 144 or seconds != list(range(600, 86401, 600)):
            raise ValueError(f"{day.date()}的144个十分钟时段不完整或重复")
        expected = day + pd.to_timedelta(seconds, unit="s")
        if not pd.DatetimeIndex(group.datetime).equals(expected):
            raise ValueError(f"{day.date()}的datetime与源日期/时刻不一致")
    values = frame[["load_kwh", "pv_actual_kwh"]].to_numpy(float)
    if not np.isfinite(values).all() or (values < 0).any():
        raise ValueError("历史实际电量含缺失、非有限值或负值，停止绘图")
    return frame


def build_daily_matrix(frame):
    return tuple(frame[column].to_numpy(float).reshape(365, 144)
                 for column in ("load_kwh", "pv_actual_kwh"))


def compute_lag_similarity(load, pv, max_lag=14):
    load, pv = np.asarray(load, float), np.asarray(pv, float)
    if load.ndim != 2 or load.shape != pv.shape or not 1 <= max_lag < len(load):
        raise ValueError("日曲线矩阵尺寸或最大滞后不符")
    if not np.isfinite(load).all() or not np.isfinite(pv).all() or (load < 0).any() or (pv < 0).any():
        raise ValueError("日曲线必须为有限非负数值")
    rows = []
    for lag in range(1, max_lag + 1):
        errors = []
        for values in (load, pv):
            # 分子与分母均仅用目标日d=lag+1,...,365，不能使用全年总量作分母。
            current, previous = values[lag:], values[:-lag]
            denominator = float(current.sum())
            if denominator <= 0:
                raise ValueError(f"滞后{lag}天的有效目标日电量总和不为正")
            errors.append(float(np.abs(current - previous).sum() / denominator))
        rows.append((lag, *errors))
    return pd.DataFrame(rows, columns=["lag_days", "load_nmae", "pv_nmae"])


def plot_lag_similarity(table, folder):
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    available = {font.name for font in font_manager.fontManager.ttflist}
    font = next((name for name in ("Microsoft YaHei", "SimHei", "Noto Sans CJK SC", "SimSun") if name in available), None)
    if font is None:
        raise ValueError("未找到中文字体，请安装Microsoft YaHei、SimHei或Noto Sans CJK SC")
    style = {"font.family": font, "font.size": 10, "axes.unicode_minus": False,
             "pdf.fonttype": 42, "figure.facecolor": "white", "axes.facecolor": "white"}
    with plt.rc_context(style):
        figure, axes = plt.subplots(2, 1, figsize=(7, 7.1), layout="constrained")
        figure.suptitle("负荷与光伏在不同日滞后下的相似性分析", fontsize=14)
        for ax, column, title, color in zip(axes, ["load_nmae", "pv_nmae"],
                ["（a）负荷日滞后归一化平均绝对误差", "（b）光伏日滞后归一化平均绝对误差"],
                ["#285F8F", "#C87725"]):
            ax.plot(table.lag_days, table[column], color=color, marker="o", markersize=4.5, linewidth=1.6)
            for lag in (5, 7, 14):
                ax.axvline(lag, color="#888888", linestyle="--", linewidth=.9, alpha=.8, zorder=0)
            ax.set(title=title, xlabel="滞后天数 l（天）", ylabel="归一化平均绝对误差", xticks=range(1, 15))
            # 仅设零下界，上界由数据自然确定；不突出或手工制造周期低点。
            ax.set_ylim(bottom=0)
            ax.grid(axis="y", alpha=.2)
            ax.spines[["top", "right"]].set_visible(False)
        try:
            for suffix in ("png", "pdf"):
                figure.savefig(folder / f"q2_lag_similarity.{suffix}", dpi=300, facecolor="white")
        finally:
            plt.close(figure)
