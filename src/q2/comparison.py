"""保留旧版完整结果，独立生成新旧模型对照，绝不重写历史存档。"""

import json
from pathlib import Path
from shutil import copy2

import pandas as pd

from src.common.data_loader import file_hash
from src.q2.optimizer import SOC_MIN, VALIDATION_TOL

PAPER_DATES = ("2025-03-20", "2025-06-21", "2025-09-23", "2025-12-21")


def archive_expost(root):
    root = Path(root)
    archive = root / "outputs/comparison/archive/q2_expost"
    manifest = archive / "archive_sha256.json"
    if manifest.exists():
        hashes = json.loads(manifest.read_text(encoding="utf-8"))
        if any(file_hash(archive / name) != value for name, value in hashes.items()):
            raise RuntimeError("旧Q2存档哈希不一致")
        return archive
    output = root / "outputs/q2"
    metrics = json.loads((output / "q2_metrics.json").read_text(encoding="utf-8"))
    if metrics.get("actual_operation_mode") == "rolling_horizon_causal":
        raise RuntimeError("未找到旧版存档，禁止将滚动结果冒充旧版")
    archive.mkdir(parents=True, exist_ok=True)
    files = [p for p in output.iterdir() if p.is_file()] + [root / "outputs/submissions/result2.xlsx"]
    hashes = {}
    for source in files:
        destination = archive / source.name
        if destination.exists() and file_hash(source) != file_hash(destination):
            raise RuntimeError("存档存在同名不同内容文件，停止覆盖")
        copy2(source, destination)
        hashes[source.name] = file_hash(source)
        if hashes[source.name] != file_hash(destination):
            raise RuntimeError("旧Q2存档复制不一致")
    manifest.write_text(json.dumps(hashes, indent=2), encoding="utf-8")
    return archive


def comparison_values(metrics, daily):
    keys = ("total_planned_grid_purchase_kwh", "total_emergency_purchase_kwh", "total_planned_cost_yuan",
            "total_emergency_cost_yuan", "total_actual_cost_yuan", "emergency_purchase_day_count",
            "emergency_purchase_slot_count", "initial_soc_kwh", "final_soc_kwh",
            "minimum_actual_soc_kwh", "maximum_actual_soc_kwh")
    values = {k: metrics[k] for k in keys}
    values["days_ending_at_soc_min_within_tolerance"] = int((abs(daily.soc_actual_end_kwh - SOC_MIN) <= VALIDATION_TOL).sum())
    values["average_day_end_soc_kwh"] = float(daily.soc_actual_end_kwh.mean())
    for day in PAPER_DATES:
        values[f"emergency_purchase_kwh_{day}"] = float(daily.loc[daily.date == day, "emergency_purchase_kwh"].iloc[0])
    return values


def write_comparison(root, metrics, daily):
    root = Path(root)
    archive = root / "outputs/comparison/archive/q2_expost"
    old = comparison_values(json.loads((archive / "q2_metrics.json").read_text(encoding="utf-8")),
                            pd.read_csv(archive / "q2_daily_metrics.csv", float_precision="round_trip"))
    new = comparison_values(metrics, daily)
    rows = {key: {"old": old[key], "new": new[key], "absolute_difference": new[key] - old[key],
                  "percentage_difference": (new[key] - old[key]) / old[key] * 100 if abs(old[key]) > VALIDATION_TOL else None}
            for key in old}
    report = {"old_operation_mode": "ex-post perfect foresight", "new_operation_mode": "causal rolling horizon",
              "difference_definition": "new minus old; percentage null when old is numerically zero",
              "comparison": rows}
    folder = root / "outputs/comparison"
    (folder / "q2_expost_vs_rolling.json").write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    text = ["# Q2 旧完美预见与新因果滚动比较", "", "旧版仅供对照；新版滚动结果为正式Q2输出。差值为新减旧。", "",
            "| 指标 | 旧版 | 新版 | 差值 | 变化率（%） |", "|---|---:|---:|---:|---:|"]
    for key, row in rows.items():
        percent = "不适用（旧值近零）" if row["percentage_difference"] is None else f"{row['percentage_difference']:.6f}"
        text.append(f"| {key} | {row['old']:.8f} | {row['new']:.8f} | {row['absolute_difference']:.8f} | {percent} |")
    (folder / "q2_expost_vs_rolling.md").write_text("\n".join(text) + "\n", encoding="utf-8")
    return report
