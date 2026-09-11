"""Q2严格按预测、日前承诺、实际运行、状态传递的顺序逐日执行。"""

import argparse
from datetime import timedelta
import json
from pathlib import Path
import sys
from time import perf_counter

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.common.data_loader import file_hash
from src.q2.forecasting import FORMAL_DATES, K_PV, M_LOAD, forecast_day, load_daily_inputs, nmae
from src.q2.optimizer import COST_LOCK_TOLERANCE, INITIAL_SOC, SOC_MIN, SOLVER_FEASTOL, VALIDATION_TOL, solve_plan, validate_schedule
from src.q2.rolling import TERMINAL_GAP_LOCK_TOLERANCE, solve_actual_rolling_day
from src.q2.comparison import archive_expost, write_comparison
from src.q2.risk import historical_risk


def summarize(predictions, plan, actual, daily, windows):
    emergency = actual.emergency_purchase_kwh > VALIDATION_TOL
    return {
        "formal_start_date": daily.date.iloc[0], "formal_end_date": daily.date.iloc[-1],
        "number_of_days": len(daily), "number_of_slots": len(actual),
        "total_planned_grid_purchase_kwh": float(plan.grid_purchase_plan_kwh.sum()),
        "total_emergency_purchase_kwh": float(actual.emergency_purchase_kwh.sum()),
        "total_planned_cost_yuan": float(actual.planned_cost_slot_yuan.sum()),
        "total_emergency_cost_yuan": float(actual.emergency_cost_slot_yuan.sum()),
        "total_actual_cost_yuan": float(actual.total_cost_slot_yuan.sum()),
        "emergency_purchase_day_count": int(actual.loc[emergency, "date"].nunique()),
        "emergency_purchase_slot_count": int(emergency.sum()),
        "initial_soc_kwh": float(actual.soc_real_start_kwh.iloc[0]),
        "final_soc_kwh": float(actual.soc_real_end_kwh.iloc[-1]),
        "minimum_actual_soc_kwh": float(min(actual.soc_real_start_kwh.min(), actual.soc_real_end_kwh.min())),
        "maximum_actual_soc_kwh": float(max(actual.soc_real_start_kwh.max(), actual.soc_real_end_kwh.max())),
        "maximum_plan_constraint_violation": float(daily.max_plan_constraint_violation.max()),
        "maximum_actual_constraint_violation": float(daily.max_actual_constraint_violation.max()),
        "maximum_cross_day_soc_violation": float(np.max(np.abs(daily.soc_start_kwh.to_numpy()[1:] - daily.soc_actual_end_kwh.to_numpy()[:-1]), initial=0)),
        "load_window_selection_counts": {str(k): int(v) for k, v in windows.load_window_weeks.value_counts().sort_index().items()},
        "pv_window_selection_counts": {str(k): int(v) for k, v in windows.pv_window_days.value_counts().sort_index().items()},
        "overall_load_forecast_nmae": nmae(predictions.load_actual_kwh, predictions.load_forecast_kwh),
        "overall_pv_forecast_nmae": nmae(predictions.pv_actual_kwh, predictions.pv_forecast_kwh),
        "simultaneous_plan_charge_discharge_slots": int(daily.simultaneous_plan_charge_discharge_slots.sum()),
        "simultaneous_actual_charge_discharge_slots": int(daily.simultaneous_actual_charge_discharge_slots.sum()),
        "solver_status_counts": {col: daily[col].value_counts().to_dict() for col in
                                 ["plan_primary_status", "plan_secondary_status"]},
        "actual_operation_mode": "rolling_horizon_causal",
        "total_rolling_steps": len(actual), "total_actual_lp_optimizations": len(actual) * 3,
        **{f"rolling_{stage}_status_counts": actual[f"rolling_{stage}_status"].value_counts().to_dict()
           for stage in ("primary", "secondary", "tertiary")},
        "days_ending_at_soc_min_within_tolerance": int((abs(daily.soc_actual_end_kwh - SOC_MIN) <= VALIDATION_TOL).sum()),
        "average_day_start_soc_kwh": float(daily.soc_start_kwh.mean()),
        "average_day_end_soc_kwh": float(daily.soc_actual_end_kwh.mean()),
        "average_actual_end_soc_deficit_kwh": float(daily.actual_end_soc_deficit_kwh.mean()),
        "maximum_actual_end_soc_deficit_kwh": float(daily.actual_end_soc_deficit_kwh.max()),
        "maximum_rolling_constraint_violation": float(daily.max_rolling_constraint_violation.max()),
        "total_actual_executed_throughput_kwh": float(daily.actual_executed_throughput_kwh.sum()),
        "terminal_gap_lock_tolerance_kwh": TERMINAL_GAP_LOCK_TOLERANCE,
        "validation_tolerance": VALIDATION_TOL, "reporting_tolerance": VALIDATION_TOL,
        "cost_lock_tolerance_yuan": COST_LOCK_TOLERANCE, "solver_feasibility_tolerance": SOLVER_FEASTOL,
        "remaining_todos": [],
    }


def run_q2(root=ROOT, skip_workbook=False, benchmark=False):
    root = Path(root)
    # 先归档旧结果；单日基准写独立目录，不覆盖正式全年结果。
    archive_expost(root)
    output = root / ("outputs/comparison/q2_rolling_benchmark" if benchmark else "outputs/q2")
    output.mkdir(parents=True, exist_ok=True)
    frozen = sorted(set(list((root / "data/raw").rglob("*.xlsx")) + list((root / "data/processed").glob("*.csv"))
                        + list((root / "outputs/schedule").glob("q1*")) + list((root / "outputs/metrics").glob("q1*"))
                        + list((root / "outputs/figures/q1").glob("*")) + list((root / "src/q1").glob("*.py"))
                        + [root / "outputs/submissions/result1.xlsx", root / "src/q2/forecasting.py", root / "src/q2/risk.py"]))
    before = {p: file_hash(p) for p in frozen if p.is_file()}
    all_days, price = load_daily_inputs(root / "data/processed/historical_power.csv", root / "data/processed/q1_input.csv")
    history, residuals, cache = {}, {}, {}
    predictions, plans, actuals, daily, windows, warmup, warmup_windows = [], [], [], [], [], [], []
    start_soc = INITIAL_SOC
    first_forecast = min(all_days) + timedelta(days=max(max(M_LOAD) * 7, max(K_PV)) + 1)
    february_errors = None
    for day in sorted(all_days):
        if day < first_forecast:
            history[day] = all_days[day]
            continue
        day_tick = perf_counter()
        # 此处 history 和 residuals 均只含已经完成的日期，目标日尚未进入信息集。
        assert all(past < day for past in history) and all(past < day for past in residuals)
        forecast, selection = forecast_day(history, day, cache)
        baseline = forecast["load"] - forecast["pv"]
        formal = day in FORMAL_DATES
        if formal:
            risk, error_dates = historical_risk(residuals, day)
            if february_errors is None:
                february_errors = [d.isoformat() for d in error_dates]
            risk_load = baseline + risk
            plan, pm = solve_plan(risk_load, forecast["pv"], price, start_soc, day)
            commitment = plan.grid_purchase_plan_kwh.to_numpy(copy=True)
            commitment.setflags(write=False)
            # 日前承诺冻结后，观察接口每次仅揭示当前时段；预测在日循环内不更新。
            observed = all_days[day]
            def observe_current(slot):
                return float(observed["load"][slot-1]), float(observed["pv"][slot-1])
            actual, am = solve_actual_rolling_day(observe_current, forecast["load"], forecast["pv"],
                                                   price, commitment, start_soc, day)
            if not np.array_equal(actual.grid_purchase_plan_kwh.to_numpy(), commitment):
                raise RuntimeError("实际运行更改了普通购电承诺")
            selection.update(historical_error_sample_count=len(error_dates),
                             residual_first_date=error_dates[0].isoformat(), residual_last_date=error_dates[-1].isoformat(),
                             residual_dates="|".join(d.isoformat() for d in error_dates))
            windows.append(selection)
        else:
            # 一月仅建立满足同样动态选窗规则的伪预测，不构造无效日期的残差。
            observed = all_days[day]
            warmup_windows.append(selection)
        prediction = pd.DataFrame({"date": day.isoformat(), "slot": np.arange(1, 145), "source_time": observed["source_time"],
                                   "load_actual_kwh": observed["load"], "pv_actual_kwh": observed["pv"],
                                   "load_forecast_kwh": forecast["load"], "pv_forecast_kwh": forecast["pv"],
                                   "baseline_net_load_kwh": baseline,
                                   "selected_load_window_weeks": selection["load_window_weeks"],
                                   "selected_pv_window_days": selection["pv_window_days"]})
        error = observed["load"] - observed["pv"] - baseline
        prediction["baseline_error_kwh"] = error
        if formal:
            prediction["risk_quantile_kwh"] = risk
            prediction["risk_adjusted_net_load_kwh"] = risk_load
            prediction["historical_error_sample_count"] = len(error_dates)
            predictions.append(prediction)
            plan["source_time"] = observed["source_time"]
            actual["source_time"] = observed["source_time"]
            plans.append(plan)
            actuals.append(actual)
            row = {"date": day.isoformat(), "selected_load_window": selection["load_window_weeks"],
                   "selected_pv_window": selection["pv_window_days"], "soc_start_kwh": start_soc,
                   "soc_plan_end_kwh": float(plan.soc_plan_end_kwh.iloc[-1]),
                   "soc_actual_end_kwh": float(actual.soc_real_end_kwh.iloc[-1]),
                   "planned_grid_purchase_kwh": float(commitment.sum()), "emergency_purchase_kwh": float(actual.emergency_purchase_kwh.sum()),
                   "planned_cost_yuan": float(actual.planned_cost_slot_yuan.sum()), "emergency_cost_yuan": float(actual.emergency_cost_slot_yuan.sum()),
                   "total_cost_yuan": float(actual.total_cost_slot_yuan.sum()),
                   "plan_secondary_throughput_kwh": pm["throughput"], "actual_executed_throughput_kwh": am["throughput"],
                   "actual_end_soc_deficit_kwh": max(0., start_soc - float(actual.soc_real_end_kwh.iloc[-1])),
                   "actual_rolling_solve_count": len(actual),
                   **{f"rolling_{stage}_optimal_count": int(actual[f"rolling_{stage}_status"].eq("optimal").sum())
                      for stage in ("primary", "secondary", "tertiary")},
                   "rolling_terminal_gap_min_kwh": float(actual.rolling_terminal_gap_star_kwh.min()),
                   "rolling_terminal_gap_max_kwh": float(actual.rolling_terminal_gap_star_kwh.max()),
                   "rolling_terminal_gap_last_kwh": float(actual.rolling_terminal_gap_star_kwh.iloc[-1]),
                   "max_actual_executed_constraint_violation": am["max_violation"],
                   "max_rolling_constraint_violation": am["max_rolling_violation"],
                   "actual_optimize_seconds": am["optimize_seconds"], "actual_elapsed_seconds": am["elapsed_seconds"],
                   "max_plan_constraint_violation": pm["max_violation"], "max_actual_constraint_violation": am["max_violation"],
                   "simultaneous_plan_charge_discharge_slots": pm["simultaneous_slots"],
                   "simultaneous_actual_charge_discharge_slots": am["simultaneous_slots"],
                   "risk_error_sample_min": len(error_dates), "risk_error_sample_max": len(error_dates)}
            for name, checked in [("plan", pm), ("actual", am)]:
                if name == "plan":
                    for key in ("primary_status", "secondary_status", "primary_star", "primary_recomputed", "secondary_objective"):
                        row[f"{name}_{key}"] = checked[key]
                row.update({f"{name}_violation_{key}": value for key, value in checked["violations"].items()})
            daily.append(row)
            start_soc = row["soc_actual_end_kwh"]
            if len(daily) % 5 == 0 or len(daily) == 1 or day == FORMAL_DATES[-1]:
                print(f"Q2 rolling completed {len(daily)}/334 days: {day} ({am['elapsed_seconds']:.2f}s/day)", flush=True)
        else:
            warmup.append(prediction)
        # 只有当天真实运行完成后，观测及已实现残差才可被后续日期使用。
        history[day] = observed
        residuals[day] = error
        if benchmark and formal:
            benchmark_day_seconds = perf_counter() - day_tick
            break
    predictions, plan, actual = [pd.concat(parts, ignore_index=True) for parts in (predictions, plans, actuals)]
    daily, windows = pd.DataFrame(daily), pd.DataFrame(windows)
    expected_days = 1 if benchmark else 334
    if len(actual) != expected_days * 144 or len(daily) != expected_days or daily.soc_start_kwh.iloc[0] != 6000:
        raise RuntimeError("Q2 正式输出范围或初始SOC不符")
    if not np.allclose(daily.soc_start_kwh.iloc[1:], daily.soc_actual_end_kwh.iloc[:-1], rtol=0, atol=VALIDATION_TOL):
        raise RuntimeError("Q2 跨日实际SOC传递不一致")
    tables = {"q2_window_selection.csv": windows, "q2_predictions.csv": predictions,
              "q2_plan_schedule.csv": plan, "q2_actual_schedule.csv": actual, "q2_daily_metrics.csv": daily,
              "q2_warmup_predictions.csv": pd.concat(warmup, ignore_index=True),
              "q2_warmup_windows.csv": pd.DataFrame(warmup_windows)}
    for name, table in tables.items():
        if table.isna().any().any():
            raise RuntimeError(f"{name}存在意外缺失")
        table.to_csv(output / name, index=False, encoding="utf-8")
    # 从磁盘重新读回，逐日独立复核后才允许填写正式模板。
    plan = pd.read_csv(output / "q2_plan_schedule.csv", float_precision="round_trip")
    actual = pd.read_csv(output / "q2_actual_schedule.csv", float_precision="round_trip")
    for index, row in daily.iterrows():
        for mode, table in [("plan", plan), ("actual", actual)]:
            objectives = (row.plan_primary_star, row.plan_secondary_objective) if mode == "plan" else ()
            check = validate_schedule(table.iloc[index * 144:(index + 1) * 144], mode, row.soc_start_kwh, *objectives)
            if check["max_violation"] > VALIDATION_TOL:
                raise RuntimeError(f"{row.date} {mode} CSV复核失败")
    metrics = summarize(predictions, plan, actual, daily, windows)
    metrics["february_1_residual_dates"] = february_errors
    metrics["submission_status"] = "not_written"
    (output / "q2_metrics.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    if benchmark:
        metrics["benchmark_total_day_seconds"] = benchmark_day_seconds
        metrics["benchmark_actual_optimize_seconds"] = float(daily.actual_optimize_seconds.sum())
        metrics["benchmark_actual_elapsed_seconds"] = float(daily.actual_elapsed_seconds.sum())
        metrics["estimated_year_actual_seconds"] = metrics["benchmark_actual_elapsed_seconds"] * 334
    if not skip_workbook and not benchmark:
        from src.q2.result_writer import write_outputs
        write_outputs(root / "data/raw/附件5/result2.xlsx", root / "outputs/submissions/result2.xlsx",
                      plan, actual, daily, output / "q2_paper_tables.md")
        metrics["submission_status"] = "written"
    after = {p: file_hash(p) for p in before}
    if before != after:
        raise RuntimeError("Q1/预处理/官方文件完整性检查失败")
    metrics["frozen_data_unchanged"] = True
    (output / "q2_metrics.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    integrity = {str(p.relative_to(root)): {"before": before[p], "after": after[p]} for p in before}
    (output / "q2_integrity.json").write_text(json.dumps(integrity, ensure_ascii=False, indent=2), encoding="utf-8")
    if not benchmark:
        write_comparison(root, metrics, daily)
    print(json.dumps(metrics, ensure_ascii=False, indent=2), flush=True)
    return metrics


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Q2 动态预测、风险修正、计划与实际滚动运行")
    parser.add_argument("--skip-workbook", action="store_true", help="分阶段检查CSV，暂不生成模板副本")
    parser.add_argument("--benchmark", action="store_true", help="只运行2月1日，写独立对比目录并估计全年耗时")
    args = parser.parse_args()
    run_q2(skip_workbook=args.skip_workbook, benchmark=args.benchmark)
