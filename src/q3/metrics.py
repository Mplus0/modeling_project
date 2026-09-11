"""Q3参考测试结算与可复算数据输出，不计算最终参数评分。"""

import json

import numpy as np

from src.q3.confidence import EPSILON
from src.q3.optimizer import VALIDATION_TOL


def write_outputs(outputs, directory, integrity):
    directory.mkdir(parents=True, exist_ok=True)
    for name, frame in outputs.items():
        if frame.isna().any().any():
            raise ValueError(f"Q3 {name}输出含意外缺失值")
        frame.to_csv(directory/f"q3_{name}.csv",index=False,encoding="utf-8-sig")
    daily = outputs["daily_metrics"]
    actual = outputs["actual_schedule"]
    metrics = dict(run_label="TEST / REFERENCE ONLY",date_start=str(daily.date.iloc[0]),date_end=str(daily.date.iloc[-1]),
                   days=len(daily),slots=len(actual),alpha=float(daily.alpha.iloc[0]),
                   **{"lambda":float(daily["lambda"].iloc[0])}, W_c=7,W_s=14,epsilon=EPSILON,
                   validation_tolerance=VALIDATION_TOL,
                   total_actual_cost_yuan=float(daily.total_actual_cost_yuan.sum()),
                   total_emergency_purchase_kwh=float(daily.actual_emergency_purchase_kwh.sum()),
                   total_emergency_cost_yuan=float(daily.actual_emergency_cost_yuan.sum()),
                   emergency_slot_count=int(daily.emergency_slot_count.sum()),
                   daily_cost_std_yuan=float(np.std(daily.total_actual_cost_yuan,ddof=0)),
                   initial_soc_kwh=float(daily.soc_start_kwh.iloc[0]),final_soc_kwh=float(daily.soc_end_kwh.iloc[-1]),
                   min_soc_kwh=float(daily.soc_min_kwh.min()),max_soc_kwh=float(daily.soc_max_kwh.max()),
                   simultaneous_slots=int(daily.simultaneous_slots.sum()),
                   max_constraint_violation=float(daily.max_constraint_violation.max()),
                   cross_day_soc_max_difference=float(max([0.]+[abs(float(daily.soc_start_kwh.iloc[i])-float(daily.soc_end_kwh.iloc[i-1])) for i in range(1,len(daily))])),
                   plan_terminal_soc_rule="最新有效滚动计划的场景概率加权期望；当前等概率场景等价于算术平均",
                   integrity=integrity)
    (directory/"q3_single_metrics.json").write_text(json.dumps(metrics,ensure_ascii=False,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    return metrics
