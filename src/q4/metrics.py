"""Q4输出及真实费用指标，禁止把预测目标或风险项记为实际费用。"""

import json
import pandas as pd
from src.q3.search_runner import save_json
from src.q4.validation import validate_outputs


def write_outputs(directory, outputs, variant, runtime, label, integrity, formal=False):
    validation = validate_outputs(outputs,variant,formal)
    daily = outputs["daily_metrics"]
    metrics = dict(validation,variant=variant,run_label=label,runtime_seconds=runtime,
                   total_actual_cost_yuan=float(daily.total_actual_cost_yuan.sum()),
                   total_emergency_purchase_kwh=float(daily.actual_emergency_purchase_kwh.sum()),
                   total_emergency_cost_yuan=float(daily.actual_emergency_cost_yuan.sum()),
                   total_plan_cost_real_yuan=float(daily.plan_cost_00_yuan.sum()),
                   total_adjustment_cost_real_yuan=float(daily.adjustment_cost_total_yuan.sum()),
                   emergency_slot_count=int(daily.emergency_slot_count.sum()),
                   emergency_day_count=int((daily.emergency_slot_count>0).sum()),
                   daily_cost_std_yuan=float(daily.total_actual_cost_yuan.std(ddof=0)),
                   initial_soc_kwh=float(daily.soc_start_kwh.iloc[0]),final_soc_kwh=float(daily.soc_end_kwh.iloc[-1]),
                   minimum_soc_kwh=float(daily.soc_min_kwh.min()),maximum_soc_kwh=float(daily.soc_max_kwh.max()),
                   simultaneous_slots=int(daily.simultaneous_slots.sum()),
                   formal=bool(formal),validation_tolerance=1e-6,sha256_unchanged=True,protected_sha256=integrity)
    if variant==3:
        metrics.update(alpha=float(daily.alpha.iloc[0]),**{"lambda":float(daily["lambda"].iloc[0])})
    plans = outputs["plan_schedule" if variant==2 else "plan_updates"]
    rounds = plans.drop_duplicates(["date"] if variant==2 else ["date","update_time"])
    metrics["solver_status_counts"] = {f"plan_{s}":rounds[f"{s}_status"].value_counts().to_dict()
                                       for s in ("primary","secondary")}
    metrics["solver_status_counts"].update({f"actual_{s}":outputs["actual_schedule"][f"rolling_{s}_status"].value_counts().to_dict()
                                           for s in ("primary","secondary","tertiary")})
    metrics["chosen_price_window_counts"] = {str(k):int(v) for k,v in outputs["price_selection"].chosen_price_window_weeks.value_counts().items()}
    directory.mkdir(parents=True,exist_ok=True)
    for key,frame in outputs.items():
        frame.to_csv(directory/f"q4_{key}.csv",index=False,encoding="utf-8-sig")
    metrics["output_tables"] = list(outputs)
    save_json(directory/"q4_metrics.json",metrics)
    save_json(directory/"q4_validation.json",validation)
    return metrics


def load_outputs(directory):
    metrics = json.loads((directory/"q4_metrics.json").read_text(encoding="utf-8"))
    return {key:pd.read_csv(directory/f"q4_{key}.csv",float_precision="round_trip") for key in metrics["output_tables"]},metrics
