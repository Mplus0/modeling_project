"""读取冻结Q2/Q3年度指标，生成论文用相对效果对比图。"""

from pathlib import Path
import json
import warnings

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
Q2_PATH = ROOT / "outputs/q2/q2_metrics.json"
Q3_PATH = ROOT / "outputs/q3/final/q3_annual_metrics.json"
OUT_DIR = ROOT / "outputs/figures/q3"

METRICS = [
    ("total_actual_cost_yuan", "全年实际总费用", "yuan"),
    ("total_emergency_purchase_kwh", "紧急购电量", "kWh"),
    ("total_emergency_cost_yuan", "紧急购电费用", "yuan"),
    ("emergency_purchase_slot_count", "紧急购电时段数", "10 min slots"),
]
Q3_KEYS = ["total_actual_cost_yuan", "total_emergency_purchase_kwh",
           "total_emergency_cost_yuan", "emergency_slot_count"]


def _read(path):
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def _validate(data2, data3):
    if data3.get("run_label") != "Q3 FINAL":
        raise ValueError("Q3数据不是Q3 FINAL，停止绘图")
    if not (np.isclose(data3.get("alpha"), .85) and np.isclose(data3.get("lambda"), .25)):
        raise ValueError("Q3最终参数必须为alpha=0.85、lambda=0.25")
    for data, name in ((data2, "Q2"), (data3, "Q3")):
        start = data.get("formal_start_date", data.get("date_start"))
        end = data.get("formal_end_date", data.get("date_end"))
        days = data.get("number_of_days", data.get("days"))
        slots = data.get("number_of_slots", data.get("slots"))
        if (start, end, days, slots) != ("2025-02-01", "2025-12-31", 334, 48096):
            raise ValueError(f"{name}不是2025-02-01至2025-12-31的334天/48096时段结果")
    q2_keys = ["total_actual_cost_yuan", "total_emergency_purchase_kwh",
               "total_emergency_cost_yuan", "emergency_purchase_slot_count"]
    q3_keys = ["total_actual_cost_yuan", "total_emergency_purchase_kwh",
               "total_emergency_cost_yuan", "emergency_slot_count"]
    if not all(k in data2 for k in q2_keys) or not all(k in data3 for k in q3_keys):
        raise KeyError("Q2/Q3正式指标字段不完整")


def build_table(q2, q3):
    _validate(q2, q3)
    rows = []
    for (key, metric_cn, unit), q3_key in zip(METRICS, Q3_KEYS):
        q2_value = float(q2[key]) if key != "emergency_purchase_slot_count" else float(q2[key])
        q3_value = float(q3[q3_key])
        if q2_value <= 0 or not np.isfinite([q2_value, q3_value]).all():
            raise ValueError(f"{metric_cn}原始值必须为正且有限")
        ratio = q3_value / q2_value * 100.0
        rows.append(dict(metric=key, metric_cn=metric_cn, unit=unit,
                         q2_raw=q2_value, q3_raw=q3_value,
                         q2_relative_percent=100.0,
                         q3_relative_percent=ratio,
                         q3_vs_q2_change_percent=(q3_value-q2_value)/q2_value*100.0,
                         q3_vs_q2_reduction_percent=(1.0-q3_value/q2_value)*100.0))
    return pd.DataFrame(rows)


def _configure_font():
    available = {name.lower() for name in font_manager.get_font_names()}
    for candidate in ("Microsoft YaHei", "SimHei", "Noto Sans CJK SC", "Source Han Sans SC", "Arial Unicode MS"):
        if candidate.lower() in available:
            matplotlib.rcParams["font.sans-serif"] = [candidate]
            return candidate
    warnings.warn("未找到常见中文字体，图片中的中文可能需要在论文环境重新渲染", RuntimeWarning)
    matplotlib.rcParams["font.sans-serif"] = ["DejaVu Sans"]
    return None


def plot(table, destination):
    destination.parent.mkdir(parents=True, exist_ok=True)
    _configure_font()
    x = np.arange(len(table))
    width = .34
    fig, ax = plt.subplots(figsize=(10.5, 5.8), dpi=320)
    fig.patch.set_facecolor("white")
    ax.set_facecolor("white")
    q2bars = ax.bar(x-width/2, table.q2_relative_percent, width, label="问题二", color="#5B8FF9", edgecolor="white", linewidth=.6)
    q3bars = ax.bar(x+width/2, table.q3_relative_percent, width, label="问题三", color="#61DDAA", edgecolor="white", linewidth=.6)
    ax.axhline(100, color="#9AA5B1", linestyle=(0,(4,3)), linewidth=1.0, zorder=0)
    ax.set_xticks(x, table.metric_cn)
    ax.set_ylabel("相对水平（问题二 = 100%） / %")
    ax.set_ylim(0, max(112, float(table.q2_relative_percent.max()) + 9))
    ax.grid(axis="y", color="#E9EDF2", linewidth=.7)
    ax.set_axisbelow(True)
    ax.spines[["top", "right"]].set_visible(False)
    ax.spines["left"].set_color("#B8C1CC")
    ax.spines["bottom"].set_color("#B8C1CC")
    ax.legend(frameon=False, loc="upper right", ncol=2)
    for bars in (q2bars, q3bars):
        for bar in bars:
            value = bar.get_height()
            ax.text(bar.get_x()+bar.get_width()/2, value+1.0, f"{value:.2f}%",
                    ha="center", va="bottom", fontsize=9)
    fig.tight_layout()
    fig.savefig(destination, dpi=320, facecolor="white", bbox_inches="tight")
    plt.close(fig)


def main(root=ROOT):
    root = Path(root)
    q2, q3 = _read(root / Q2_PATH.relative_to(ROOT)), _read(root / Q3_PATH.relative_to(ROOT))
    table = build_table(q2, q3)
    out_dir = root / "outputs/figures/q3"
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / "q2_q3_annual_relative_comparison.csv"
    png_path = out_dir / "q2_q3_annual_relative_comparison.png"
    table.to_csv(csv_path, index=False, encoding="utf-8-sig")
    plot(table, png_path)
    print("指标\tQ2原始值\tQ3原始值\tQ3/Q2相对水平\tQ3相对Q2变化率")
    for row in table.itertuples(index=False):
        print(f"{row.metric_cn}\t{row.q2_raw:.12f}\t{row.q3_raw:.12f}\t"
              f"{row.q3_relative_percent:.6f}%\t{row.q3_vs_q2_change_percent:.6f}%")
    print(f"Q3 alpha={q3['alpha']}, lambda={q3['lambda']}")
    print("Q2日期范围=2025-02-01至2025-12-31；Q3日期范围=2025-02-01至2025-12-31")
    print(f"PNG: {png_path}\nCSV: {csv_path}")
    return table


if __name__ == "__main__":
    main()
