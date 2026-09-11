"""仅从冻结 Q1 结果生成论文图，不调用求解器或改写数值文件。"""

import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
from matplotlib import font_manager, pyplot as plt
import numpy as np
import pandas as pd

from src.common.data_loader import file_hash

FIGURES = [
    ("q1_figure1_price_grid_purchase", "电价与计划购电量时序变化", "price_yuan_per_kwh、grid_purchase_kwh", "展示电价与计划购电量的时序关系，可分析调度的经济响应；不据此声称低价必然对应高购电量。"),
    ("q1_figure2_load_pv", "小区负荷与光伏预测功率", "load_kw、pv_forecast_kw", "展示输入功率的日内供需特征；光伏为预测值，不是实测曲线或预测精度评价。"),
    ("q1_figure3_battery_charge_discharge", "储能设备充放电时序", "charge_input_kwh、z_kwh", "正柱为充电端输入 x+q，负柱为实际送达负载的放电量 −z，用于识别储能运行阶段。"),
    ("q1_figure4_soc", "储能设备储电量变化", "soc_previous_kwh 首值、soc_kwh", "展示初末储电量及上下界，用于说明储能状态变化与容量利用。"),
    ("q1_figure5_grid_purchase_structure", "外网购电用途分解", "x_kwh、y_kwh", "分解购电用于储能与直接供负荷的比例，堆叠不包含光伏 q；篇幅有限时可放附录。"),
]
TICKS = np.arange(0, 145, 24)
TICK_LABELS = [f"{h}:00" for h in range(0, 25, 4)]


def prepare_plot_data(inputs, schedule, metrics):
    required = ["price_yuan_per_kwh", "load_kw", "pv_forecast_kw", "x_kwh", "y_kwh", "q_kwh", "z_kwh",
                "grid_purchase_kwh", "charge_input_kwh", "soc_previous_kwh", "soc_kwh"]
    tolerance = float(metrics["validation_tolerance"])
    if not np.isfinite(tolerance) or not 0 < tolerance <= 1e-6:
        raise ValueError("绘图验证容差无效")
    for name, frame, columns in [("输入", inputs, required[:3]), ("调度", schedule, required)]:
        if len(frame) != 144 or "slot" not in frame or frame["slot"].tolist() != list(range(1, 145)):
            raise ValueError(f"Q1 {name}须包含按序排列的 144 个 slot")
        for column in columns:
            if column not in frame or not pd.api.types.is_numeric_dtype(frame[column]) or not np.isfinite(frame[column]).all():
                raise ValueError(f"Q1 {name}列 {column} 缺失或包含非有限数值")
    def matches(actual, expected, message):
        if not np.allclose(actual, expected, rtol=0, atol=tolerance):
            raise ValueError(message)
    for column in required[:3]:
        matches(inputs[column], schedule[column], f"输入和调度的 {column} 不一致")
    matches(schedule["grid_purchase_kwh"], schedule["x_kwh"] + schedule["y_kwh"], "购电量与 x+y 不一致")
    matches(schedule["charge_input_kwh"], schedule["x_kwh"] + schedule["q_kwh"], "充电量与 x+q 不一致")
    # 使用已存储的派生列，不以内部效率调整量替代外部充放电量。
    data = {column: schedule[column].to_numpy(float, copy=True) for column in required}
    states = np.r_[data["soc_previous_kwh"][0], data["soc_kwh"]]
    matches(data["soc_previous_kwh"], states[:-1], "相邻 SOC 起止值不一致")
    matches(states[[0, -1]], [6000, 6000], "初末 SOC 必须为 6000 kWh")
    if states.min() < 1200 - tolerance or states.max() > 10800 + tolerance:
        raise ValueError("SOC 超出 1200–10800 kWh 边界")
    for column in ("x_kwh", "y_kwh", "q_kwh", "z_kwh", "charge_input_kwh", "grid_purchase_kwh"):
        if data[column].min() < -tolerance:
            raise ValueError(f"{column} 存在超过容差的负值")
    # 区间量放在 slot 中点，状态量放在边界；轴上 24 个 slot 对应 4 小时。
    data["slot"] = schedule["slot"].to_numpy(copy=True)
    data["interval_positions"] = data["slot"] - 0.5
    data["state_positions"] = np.arange(145)
    data["states"] = states
    data["tolerance"] = tolerance
    return data


def load_plot_data(input_path, schedule_path, metrics_path):
    inputs = pd.read_csv(input_path, float_precision="round_trip")
    schedule = pd.read_csv(schedule_path, float_precision="round_trip")
    metrics = json.loads(Path(metrics_path).read_text(encoding="utf-8"))
    return prepare_plot_data(inputs, schedule, metrics)


def generate_figures(data, output_dir):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    available = {font.name for font in font_manager.fontManager.ttflist}
    font = next((name for name in ["Microsoft YaHei", "SimHei", "Noto Sans CJK SC", "SimSun"] if name in available), None)
    if font is None:
        raise ValueError("未找到可用中文字体，请提供 Microsoft YaHei、SimHei 或 Noto Sans CJK SC")
    style = {"font.family": font, "font.size": 10, "axes.titlesize": 13, "axes.labelsize": 11,
             "legend.fontsize": 9, "axes.unicode_minus": False, "pdf.fonttype": 42,
             "figure.facecolor": "white", "axes.facecolor": "white", "axes.spines.top": False}
    paths = []
    x = data["interval_positions"]
    blue, orange, green = "#285F8F", "#C87725", "#368875"
    def display(values):
        # 只对绘图副本中的浮点残差显示为零，绝不回写 CSV。
        return np.where(np.abs(values) < data["tolerance"], 0.0, values)
    with plt.rc_context(style):
        for number, (stem, title, _, _) in enumerate(FIGURES, 1):
            fig, ax = plt.subplots(figsize=(8.4, 4.4), layout="constrained")
            try:
                ax.set(xlim=(0, 144), xlabel="时间", xticks=TICKS, xticklabels=TICK_LABELS)
                ax.set_title(title, pad=42)
                ax.grid(axis="y", color="#E3E6E8", linewidth=0.5)
                ax.set_axisbelow(True)
                if number == 1:
                    other = ax.twinx()
                    ax.plot(x, data["price_yuan_per_kwh"], color=blue, lw=1.6, label="电价")
                    other.step(x, data["grid_purchase_kwh"], color=orange, lw=1.2, where="mid", label="计划购电量")
                    ax.set_ylabel("电价（元/kWh）", color=blue)
                    other.set_ylabel("计划购电量（kWh）", color=orange)
                    other.set_ylim(bottom=0)
                    handles = ax.lines + other.lines
                elif number == 2:
                    ax.plot(x, data["load_kw"], color=blue, lw=1.6, label="小区负荷")
                    ax.plot(x, data["pv_forecast_kw"], color=orange, lw=1.6, label="光伏预测功率")
                    ax.set(ylabel="功率（kW）", ylim=(0, None))
                elif number == 3:
                    ax.bar(x, display(data["charge_input_kwh"]), width=0.86, color=blue, label="充电量")
                    ax.bar(x, -display(data["z_kwh"]), width=0.86, color=orange, label="放电量")
                    ax.axhline(0, color="#555555", lw=0.8)
                    ax.set_ylabel("充放电量（kWh/10 min）")
                elif number == 4:
                    ax.plot(data["state_positions"], data["states"], color=blue, lw=1.8, label="储电量")
                    ax.axhline(1200, color=orange, ls="--", lw=1, label="下限 1200 kWh")
                    ax.axhline(6000, color="#777777", ls=":", lw=1, label="初始值 6000 kWh")
                    ax.axhline(10800, color=green, ls="-.", lw=1, label="上限 10800 kWh")
                    ax.scatter([0, 144], data["states"][[0, -1]], color=blue, s=22, zorder=4, clip_on=False)
                    ax.set(ylabel="储电量（kWh）", ylim=(0, 12000))
                else:
                    direct, charging = display(data["y_kwh"]), display(data["x_kwh"])
                    ax.bar(x, direct, width=0.9, color=blue, label="外网购电直接供负荷 y")
                    ax.bar(x, charging, bottom=direct, width=0.9, color=orange, label="外网购电用于储能 x")
                    ax.set(ylabel="购电量（kWh/10 min）", ylim=(0, None))
                if number == 1:
                    ax.legend(handles, [line.get_label() for line in handles], loc="lower center", bbox_to_anchor=(0.5, 1.01), ncol=2, frameon=False)
                else:
                    ax.legend(loc="lower center", bbox_to_anchor=(0.5, 1.01), ncol=2, frameon=False)
                for suffix in ("png", "pdf"):
                    path = output_dir / f"{stem}.{suffix}"
                    fig.savefig(path, dpi=300, bbox_inches="tight")
                    paths.append(path)
            finally:
                plt.close(fig)
    lines = ["# 问题一论文图片索引", "", "PNG：300 dpi；PDF：矢量版，适合论文排版与编辑。", "",
             "横轴只依据 slot 顺序：区间量位于 slot 中点，SOC 位于边界，0、24、…、144 对应 0:00、4:00、…、24:00。此为统一绘图表示，不改动源标签或官方模板映射。", "",
             "| 图 | 文件 | 使用变量 | 物理含义与论文建议 |", "|---|---|---|---|"]
    for i, (stem, title, variables, meaning) in enumerate(FIGURES, 1):
        lines.append(f"| 图{i} {title} | [PNG]({stem}.png) / [PDF]({stem}.pdf) | {variables} | {meaning} |")
    lines.extend(["", "充放电柱图使用 x+q 和 z，不使用效率调整后的内部电量；小于验证容差的残差仅在绘图副本中显示为零。",
                  "所有图仅展示已保存结果；不重新求解，不表示预测准确率。绘图数据校验通过，本阶段无新增建模待确认项。", ""])
    (output_dir / "README.md").write_text("\n".join(lines), encoding="utf-8")
    return paths


def plot_q1(input_path, schedule_path, metrics_path, output_dir):
    sources = [Path(p) for p in (input_path, schedule_path, metrics_path)]
    before = {p: file_hash(p) for p in sources}
    data = load_plot_data(*sources)
    paths = generate_figures(data, output_dir)
    if any(file_hash(p) != digest for p, digest in before.items()):
        raise RuntimeError("绘图期间 Q1 输入或结果文件发生变化")
    return paths
