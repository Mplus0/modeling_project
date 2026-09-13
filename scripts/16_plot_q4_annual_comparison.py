"""只读取 Q4-2/Q4-3 的 334 天正式结果，生成论文用全年相对效果对比图。

本脚本不调用优化器、不重新搜索参数，也不改写任何正式结果文件。
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import warnings

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
Q4_2_METRICS = ROOT / "outputs/q4/q4_2/q4_metrics.json"
Q4_3_METRICS = ROOT / "outputs/q4/reference/q4_3_a0.85_l0.25/q4_metrics.json"
OUT_DIR = ROOT / "outputs/figures/q4"

METRICS = (
    ("total_actual_cost_yuan", "实际总购电费用", "元"),
    ("total_emergency_cost_yuan", "紧急购电费用", "元"),
    ("total_emergency_purchase_kwh", "紧急购电量", "kWh"),
)


def _read_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _validate_metrics(q4_2: dict, q4_3: dict) -> None:
    for data, label, variant in ((q4_2, "Q4-2", 2), (q4_3, "Q4-3", 3)):
        if data.get("passed") is not True or data.get("formal") is not True:
            raise ValueError(f"{label} 不是通过验收的 formal 年度结果")
        if data.get("variant") != variant:
            raise ValueError(f"{label} variant 字段不一致")
        if (data.get("days"), data.get("slots")) != (334, 48096):
            raise ValueError(f"{label} 必须为 334 天、48096 个 10 分钟时段的年度结果")
        for key, metric_cn, _ in METRICS:
            if key not in data:
                raise KeyError(f"{label} 缺少指标 {key}（{metric_cn}）")
            value = float(data[key])
            if not np.isfinite(value) or value <= 0:
                raise ValueError(f"{label} 的 {metric_cn} 必须为正且有限")


def build_comparison_table(q4_2: dict, q4_3: dict) -> pd.DataFrame:
    """从正式指标自动计算 Q4-3 相对 Q4-2 的水平和下降比例。"""

    _validate_metrics(q4_2, q4_3)
    rows = []
    for key, metric_cn, unit in METRICS:
        base = float(q4_2[key])
        improved = float(q4_3[key])
        relative = improved / base * 100.0
        reduction = (1.0 - improved / base) * 100.0
        rows.append(
            {
                "metric": key,
                "metric_cn": metric_cn,
                "unit": unit,
                "q4_2_raw": base,
                "q4_3_raw": improved,
                "q4_2_relative_percent": 100.0,
                "q4_3_relative_percent": relative,
                "q4_3_vs_q4_2_reduction_percent": reduction,
            }
        )
    return pd.DataFrame(rows)


def _configure_font() -> str | None:
    available = {font.name for font in font_manager.fontManager.ttflist}
    for candidate in (
        "Microsoft YaHei",
        "SimHei",
        "Noto Sans CJK SC",
        "Source Han Sans SC",
        "SimSun",
    ):
        if candidate in available:
            matplotlib.rcParams["font.sans-serif"] = [candidate]
            return candidate
    warnings.warn(
        "未找到常见中文字体，图片中的中文可能需要在论文环境重新渲染",
        RuntimeWarning,
    )
    matplotlib.rcParams["font.sans-serif"] = ["DejaVu Sans"]
    return None


def plot_comparison(table: pd.DataFrame, output_dir: Path) -> list[Path]:
    """绘制 Q4-2=100% 的分组柱状图，并输出 PNG/PDF/SVG。"""

    output_dir.mkdir(parents=True, exist_ok=True)
    _configure_font()

    matplotlib.rcParams.update(
        {
            "font.size": 10,
            "axes.titlesize": 13,
            "axes.labelsize": 11,
            "axes.unicode_minus": False,
            "pdf.fonttype": 42,
            "svg.fonttype": "none",
            "figure.facecolor": "white",
            "axes.facecolor": "white",
        }
    )

    x = np.arange(len(table))
    width = 0.34
    blue = "#285F8F"
    orange = "#C87725"

    fig, ax = plt.subplots(figsize=(8.6, 5.0), layout="constrained")
    try:
        q42_bars = ax.bar(
            x - width / 2,
            table["q4_2_relative_percent"],
            width,
            label="Q4-2",
            color=blue,
            edgecolor="white",
            linewidth=0.6,
        )
        q43_bars = ax.bar(
            x + width / 2,
            table["q4_3_relative_percent"],
            width,
            label="Q4-3",
            color=orange,
            edgecolor="white",
            linewidth=0.6,
        )

        ax.set_xticks(x, table["metric_cn"])
        ax.set_ylabel("相对 Q4-2 / %")
        ax.set_ylim(0, 116)
        ax.axhline(100, color="#888888", linestyle="--", linewidth=0.9, zorder=0)
        ax.grid(axis="y", color="#E3E6E8", linewidth=0.5)
        ax.set_axisbelow(True)
        ax.spines[["top", "right"]].set_visible(False)
        ax.legend(frameon=False, loc="upper right", ncol=2)

        for bar in q42_bars:
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height() + 1.2,
                "100%",
                ha="center",
                va="bottom",
                fontsize=9,
            )

        for bar, reduction in zip(
            q43_bars,
            table["q4_3_vs_q4_2_reduction_percent"],
        ):
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height() + 1.2,
                f"下降 {reduction:.2f}%",
                ha="center",
                va="bottom",
                fontsize=9,
            )

        stem = "q4_2_q4_3_annual_relative_comparison"
        paths = []
        for suffix in ("png", "pdf", "svg"):
            path = output_dir / f"{stem}.{suffix}"
            fig.savefig(path, dpi=300, facecolor="white", bbox_inches="tight")
            paths.append(path)
        return paths
    finally:
        plt.close(fig)


def main() -> pd.DataFrame:
    sources = (Q4_2_METRICS, Q4_3_METRICS)
    missing = [str(path) for path in sources if not path.exists()]
    if missing:
        raise FileNotFoundError(f"缺少正式结果文件：{missing}")

    before = {path: _sha256(path) for path in sources}
    q4_2 = _read_json(Q4_2_METRICS)
    q4_3 = _read_json(Q4_3_METRICS)
    table = build_comparison_table(q4_2, q4_3)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    csv_path = OUT_DIR / "q4_2_q4_3_annual_relative_comparison.csv"
    table.to_csv(csv_path, index=False, encoding="utf-8-sig")
    figure_paths = plot_comparison(table, OUT_DIR)

    after = {path: _sha256(path) for path in sources}
    if before != after:
        raise RuntimeError("绘图过程中正式 Q4-2/Q4-3 指标文件发生变化")

    print("指标\tQ4-2原始值\tQ4-3原始值\tQ4-3相对Q4-2\t相对下降")
    for row in table.itertuples(index=False):
        print(
            f"{row.metric_cn}\t{row.q4_2_raw:.12f}\t{row.q4_3_raw:.12f}\t"
            f"{row.q4_3_relative_percent:.6f}%\t"
            f"{row.q4_3_vs_q4_2_reduction_percent:.6f}%"
        )
    print(f"CSV: {csv_path}")
    for path in figure_paths:
        print(f"FIGURE: {path}")
    return table


if __name__ == "__main__":
    main()
