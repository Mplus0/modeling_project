"""Q1 一级原始解与二级解的诊断报告，不写正式结果。"""

import json
from pathlib import Path

import pandas as pd

from src.q1.optimizer import VALIDATION_TOL, evaluate_schedule


def write_comparison(primary, secondary, metrics, output_dir):
    if any(metrics[key] != "optimal" for key in ("primary_status", "secondary_status")):
        raise ValueError("Q1 对比要求两个阶段均达到 optimal")
    # 分别从完整变量复算原约束、费用和吞吐量，不依赖求解器最优标记。
    p = evaluate_schedule(primary, metrics["C_star"], float(primary["throughput_kwh"].sum()))
    s = evaluate_schedule(secondary, metrics["C_star"], metrics["secondary_solver_objective"])
    if not p["validation_passed"] or not s["validation_passed"]:
        raise ValueError("Q1 对比调度未通过独立约束或最优费用复核")
    hp, hs = p["secondary_throughput"], s["secondary_throughput"]
    reduction = hp - hs
    if reduction < -VALIDATION_TOL:
        raise ValueError("Q1 二级吞吐量超过一级原始解")
    # 一级吞吐量数值为零时不做除法；不裁剪调度或吞吐量本身。
    percent = reduction / hp * 100 if abs(hp) > VALIDATION_TOL else 0.0
    indicators = {
        "一级原始解全天购电费用": p["primary_cost"],
        "一级原始解储能总吞吐量 H": hp,
        "一级原始解同时充放电有效时段数": p["simultaneous_charge_discharge_intervals"],
        "二级优化后全天购电费用": s["primary_cost"],
        "二级优化后储能总吞吐量 H": hs,
        "二级优化后同时充放电有效时段数": s["simultaneous_charge_discharge_intervals"],
        "储能总吞吐量下降量": reduction,
        "储能总吞吐量下降比例": percent,
    }
    provenance = ("one optimal solution returned by SCIP using only the primary cost objective; "
                  "一级原始解是 SCIP 返回的一个最优解，并非唯一一级最优解。")
    # 直接以中文键保存八项核心数值，同时保留分组字段便于程序读取。
    report = {
        **indicators,
        "core_indicators": indicators,
        "primary_cost": p["primary_cost"],
        "secondary_cost": s["primary_cost"],
        "primary_status": metrics["primary_status"], "secondary_status": metrics["secondary_status"],
        "C_star": metrics["C_star"],
        "secondary_minus_primary_cost_yuan": s["primary_cost"] - p["primary_cost"],
        "validation_tolerance": VALIDATION_TOL,
        "primary_solution_provenance": provenance,
        "definitions": "费用单位元；H=Σ[0.9(x+q)+z/0.9]，单位kWh；同充同放：(x+q)>VALIDATION_TOL且z>VALIDATION_TOL；下降比例单位%；一级H数值为零时比例记0。",
        "primary_validation": p["violations"], "secondary_validation": s["violations"],
        "validation_passed": True,
        "official_result": "现有二级优化正式结果保持不变，本报告仅用于诊断比较。",
    }
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    csv = directory / "q1_primary_only_schedule.csv"
    primary.to_csv(csv, index=False, encoding="utf-8")
    saved = pd.read_csv(csv, float_precision="round_trip", keep_default_na=False)
    if not saved.equals(primary):
        raise RuntimeError("Q1 一级快照 CSV 往返不一致")
    (directory / "q1_secondary_comparison.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    rows = ["# Q1 一级原始解与二级优化对比", "", "| 指标 | 数值 |", "| --- | ---: |"]
    rows.extend(f"| {key} | {value} |" for key, value in indicators.items())
    rows.extend(["", report["definitions"], "", provenance, "",
                 f"一级/二级状态：{report['primary_status']} / {report['secondary_status']}；C_star={report['C_star']} 元。",
                 f"二级减一级费用差={report['secondary_minus_primary_cost_yuan']} 元；验证容差={VALIDATION_TOL}。",
                 "两套调度均通过原约束及最优费用独立复核，二级吞吐量不增加。逐项残差见同名 JSON。",
                 report["official_result"], ""])
    (directory / "q1_secondary_comparison.md").write_text("\n".join(rows), encoding="utf-8")
    return report
