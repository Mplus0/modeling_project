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


def write_annual_outputs(outputs, directory, timings, integrity):
    """完整年度验收通过才写参考结果，不调用Score或最终排名。"""
    from src.q3.annual import validate_annual, ANNUAL_LABEL
    from src.q3.optimizer import SOC_MIN

    validation = validate_annual(outputs)
    daily, actual, plans = [outputs[k] for k in ("daily_metrics","actual_schedule","plan_updates")]
    metrics = dict(run_label=ANNUAL_LABEL,alpha=float(daily.alpha.iloc[0]),**{"lambda":float(daily["lambda"].iloc[0])},
                   formal_start_date=str(daily.date.iloc[0]),formal_end_date=str(daily.date.iloc[-1]),
                   days=len(daily),slots=len(actual),W_c=7,W_s=14,epsilon=EPSILON,
                   validation_tolerance=VALIDATION_TOL,reporting_tolerance=VALIDATION_TOL,
                   total_plan_cost_00_yuan=float(daily.plan_cost_00_yuan.sum()),
                   total_adjustment_cost_yuan=float(daily.adjustment_cost_total_yuan.sum()),
                   total_emergency_cost_yuan=float(daily.actual_emergency_cost_yuan.sum()),
                   total_actual_cost_yuan=float(daily.total_actual_cost_yuan.sum()),
                   total_emergency_purchase_kwh=float(daily.actual_emergency_purchase_kwh.sum()),
                   emergency_slot_count=int(daily.emergency_slot_count.sum()),
                   emergency_day_count=int((daily.emergency_slot_count>0).sum()),
                   daily_cost_mean_yuan=float(daily.total_actual_cost_yuan.mean()),
                   daily_cost_std_yuan=float(np.std(daily.total_actual_cost_yuan,ddof=0)),
                   initial_soc_kwh=float(daily.soc_start_kwh.iloc[0]),final_soc_kwh=float(daily.soc_end_kwh.iloc[-1]),
                   minimum_soc_kwh=float(daily.soc_min_kwh.min()),maximum_soc_kwh=float(daily.soc_max_kwh.max()),
                   days_ending_near_soc_min=int((np.abs(daily.soc_end_kwh-SOC_MIN)<=VALIDATION_TOL).sum()),
                   near_soc_min_tolerance_kwh=VALIDATION_TOL,average_day_end_soc_kwh=float(daily.soc_end_kwh.mean()),
                   simultaneous_slots=int(daily.simultaneous_slots.sum()),
                   actual_lp_count=len(actual)*3,plan_lp_count=len(daily)*4*2,
                   average_day_seconds=timings["engine_runtime_seconds"]/len(daily),
                   **timings,**validation,integrity=integrity)
    metrics["total_increase_adjustment_kwh"] = sum(float(daily[f"increase_{h:02d}_kwh"].sum()) for h in (6,12,18))
    metrics["total_decrease_adjustment_kwh"] = sum(float(daily[f"decrease_{h:02d}_kwh"].sum()) for h in (6,12,18))
    for hour in (6,12,18):
        metrics[f"update_{hour:02d}_count"] = int(plans[plans.update_time.eq(f"{hour:02d}:00")].date.nunique())
        metrics[f"rho_{hour:02d}_mean"] = float(daily[f"rho_{hour:02d}"].mean())
        for action in ("increase","decrease"):
            metrics[f"total_{action}_{hour:02d}_kwh"] = float(daily[f"{action}_{hour:02d}_kwh"].sum())
    rounds = plans.drop_duplicates(["date","update_time"])
    metrics["solver_status_counts"] = {f"plan_{stage}":{str(k):int(v) for k,v in rounds[f"{stage}_status"].value_counts().items()}
                                       for stage in ("primary","secondary")}
    metrics["solver_status_counts"].update({f"actual_{stage}":{str(k):int(v) for k,v in actual[f"rolling_{stage}_status"].value_counts().items()}
                                           for stage in ("primary","secondary","tertiary")})
    directory.mkdir(parents=True,exist_ok=True)
    for name,frame in outputs.items():
        frame.to_csv(directory/f"q3_{name}.csv",index=False,encoding="utf-8-sig")
    (directory/"q3_annual_metrics.json").write_text(json.dumps(metrics,ensure_ascii=False,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    return metrics
