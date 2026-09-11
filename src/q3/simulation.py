"""Q3单组参考仿真：四次计划更新、当前一步执行及跨日真实SOC传递。"""

from datetime import timedelta

import numpy as np
import pandas as pd

from src.q3.forecast import load_prediction, replay_history, update_pv, UPDATE_HOURS
from src.q3.scenarios import build_scenarios
from src.q3.optimizer import (solve_plan, solve_actual_step, validate_schedule,
                               ETA_CHARGE, ETA_DISCHARGE, VALIDATION_TOL)


def expected_terminal_soc(values, probabilities):
    values = np.asarray(values, float)
    if values.ndim != 1 or not len(values) or not np.isfinite(values).all():
        raise ValueError("Q3计划终端SOC集合不完整")
    probabilities = np.asarray(probabilities, float)
    if (probabilities.shape != values.shape or not np.isfinite(probabilities).all()
            or (probabilities < 0).any() or abs(float(probabilities.sum())-1.) > 1e-12):
        raise ValueError("Q3场景概率必须非负、完整且总和为1")
    # 最新有效计划的场景终态按概率取期望，仅作为实际层第二级参考，不约束计划终态。
    return float(np.dot(probabilities, values))


def simulate_day(date, observe_current, midnight_pv_kw, load_forecast, price, issues,
                 records, residuals, start_soc, alpha, risk_weight):
    """真实未来仅存在于观测回调内部，每次只读取当前已到达时段。"""
    if len(load_forecast) != 144 or len(price) != 144:
        raise ValueError("Q3单日必须包含144个完整时段")
    soc, current_pv, pv_forecast, grid = float(start_soc), float(midnight_pv_kw), None, None
    forecast_rows, confidence_rows, scenario_rows, plan_rows, actual_rows = [], [], [], [], []
    daily = dict(date=str(date), run_label="TEST / REFERENCE ONLY", alpha=alpha,
                 **{"lambda": risk_weight}, soc_start_kwh=soc)
    max_plan_violation = 0.
    for slot in range(1,145):
        if slot in (1,37,73,109):
            hour = (slot-1)//6
            old_pv = None if pv_forecast is None else pv_forecast.copy()
            pv_forecast, raw, conf = update_pv(date, hour, current_pv, pv_forecast, issues, records)
            scenario = build_scenarios(date, hour, load_forecast, pv_forecast, residuals, slot)
            old_grid = None if grid is None else grid[slot-1:].copy()
            plan = solve_plan(scenario["load"], scenario["pv"], np.asarray(price)[slot-1:], soc,
                              alpha, risk_weight, old_grid)
            try:
                target_soc = expected_terminal_soc(plan["scenario_terminal_soc"], scenario["probability"])
            except ValueError as exc:
                raise ValueError(f"{date} {hour:02d}:00 {exc}；场景终值={plan['scenario_terminal_soc']}") from exc
            if grid is None:
                grid = plan["grid"].copy()
            else:
                grid[slot-1:] = plan["grid"]
            daily[f"scenario_count_{hour:02d}"] = len(scenario["dates"])
            daily[f"soc_{hour:02d}_kwh"] = soc
            daily[f"plan_primary_status_{hour:02d}"] = plan["primary_status"]
            daily[f"plan_secondary_status_{hour:02d}"] = plan["secondary_status"]
            cost_key = "plan_cost_00_yuan" if hour == 0 else f"adjustment_cost_{hour:02d}_yuan"
            daily[cost_key] = plan["purchase_or_adjustment_cost"]
            daily[f"increase_{hour:02d}_kwh"] = float(plan["increase"].sum())
            daily[f"decrease_{hour:02d}_kwh"] = float(plan["decrease"].sum())
            max_plan_violation = max(max_plan_violation,plan["max_violation"])
            if conf is not None:
                confidence_rows.append(dict(date=str(date), update_time=f"{hour:02d}:00",
                                             **{k:v for k,v in conf.items() if k != "dates"},
                                             history_dates=";".join(map(str,conf["dates"]))))
                daily[f"rho_{hour:02d}"] = conf["confidence_rho"]
            for j, historical_date in enumerate(scenario["dates"]):
                scenario_rows.append(dict(date=str(date),update_time=f"{hour:02d}:00",scenario=j,
                                          history_date=str(historical_date), probability=float(scenario["probability"][j]),
                                          scenario_count=len(scenario["dates"]),
                                          terminal_soc_kwh=plan["scenario_terminal_soc"][j]))
            for j, t in enumerate(range(slot,145)):
                forecast_rows.append(dict(date=str(date),update_time=f"{hour:02d}:00",slot=t,
                                          old_forecast_kwh=float(raw[j] if old_pv is None else old_pv[t-1]),
                                          new_raw_forecast_kwh=float(raw[j]),updated_forecast_kwh=float(pv_forecast[t-1]),
                                          confidence_rho=1. if conf is None else conf["confidence_rho"],
                                          historical_error_old=0. if conf is None else conf["historical_error_old"],
                                          historical_error_new=0. if conf is None else conf["historical_error_new"]))
                plan_rows.append(dict(date=str(date),update_time=f"{hour:02d}:00",slot=t,
                                      previous_plan_kwh=float(0. if old_grid is None else old_grid[j]),
                                      new_plan_kwh=float(grid[t-1]),increase_kwh=float(plan["increase"][j]),
                                      decrease_kwh=float(plan["decrease"][j]),
                                      adjustment_cost_yuan=float(price[t-1]*(1.5*plan["increase"][j]-.5*plan["decrease"][j])),
                                      alpha=alpha,**{"lambda":risk_weight},scenario_count=len(scenario["dates"]),
                                      primary_objective=plan["primary_objective"],secondary_throughput=plan["secondary_throughput"],
                                      primary_status=plan["primary_status"],secondary_status=plan["secondary_status"],
                                      initial_soc_kwh=soc,plan_terminal_soc_kwh=target_soc,
                                      max_constraint_violation=plan["max_violation"]))
        current_load, observed_pv = observe_current(slot)
        horizon, checked = solve_actual_step(slot, current_load, observed_pv, load_forecast,
                                             pv_forecast, price, grid, soc, target_soc, date)
        row = horizon.iloc[0].to_dict()
        # 仅执行首项，下一步与下一轮计划初态均由真实动作递推。
        soc += ETA_CHARGE*(row["x_real_kwh"]+row["q_real_kwh"])-row["z_real_kwh"]/ETA_DISCHARGE
        row["soc_real_end_kwh"] = soc
        current_pv = observed_pv*6
        row.update(effective_contract_kwh=float(grid[slot-1]), load_forecast_kwh=float(load_forecast[slot-1]),
                   pv_forecast_kwh=float(pv_forecast[slot-1]), run_label="TEST / REFERENCE ONLY",
                   rolling_primary_status=checked["primary_status"],rolling_secondary_status=checked["secondary_status"],
                   rolling_tertiary_status=checked["tertiary_status"],rolling_primary_star=checked["primary_star"],
                   rolling_terminal_gap_star=checked["terminal_gap_star"],rolling_max_violation=checked["max_violation"])
        actual_rows.append(row)
    actual = pd.DataFrame(actual_rows)
    check = validate_schedule(actual,"actual",start_soc)
    if check["max_violation"] > VALIDATION_TOL:
        raise RuntimeError(f"Q3 {date} 已执行轨迹独立复核失败: {check['violations']}")
    adjustment = sum(daily[f"adjustment_cost_{h:02d}_yuan"] for h in (6,12,18))
    # 结算不包含CVaR、场景期望费用或重叠滚动目标，只累计已执行紧急购电。
    daily.update(soc_end_kwh=soc, soc_min_kwh=float(min(start_soc,actual.soc_real_end_kwh.min())),
                 soc_max_kwh=float(max(start_soc,actual.soc_real_end_kwh.max())),
                 adjustment_cost_total_yuan=adjustment,actual_emergency_purchase_kwh=float(actual.emergency_purchase_kwh.sum()),
                 actual_emergency_cost_yuan=check["cost"],
                 total_actual_cost_yuan=daily["plan_cost_00_yuan"]+adjustment+check["cost"],
                 emergency_slot_count=int((actual.emergency_purchase_kwh>VALIDATION_TOL).sum()),
                 actual_throughput_kwh=check["throughput"], simultaneous_slots=check["simultaneous_slots"],
                 max_constraint_violation=max(check["max_violation"],max_plan_violation,float(actual.rolling_max_violation.max())))
    return dict(forecast_updates=pd.DataFrame(forecast_rows),confidence=pd.DataFrame(confidence_rows),
                scenarios_summary=pd.DataFrame(scenario_rows),plan_updates=pd.DataFrame(plan_rows),
                actual_schedule=actual,daily_metrics=pd.DataFrame([daily]))


def simulate_days(history, issues, price, start_date, days, initial_soc, alpha, risk_weight):
    if days not in (1,2,3):
        raise ValueError("Q3第一阶段仅允许连续1至3日参考验证")
    outputs, current_soc = [], float(initial_soc)
    for offset in range(days):
        day = start_date+timedelta(days=offset)
        prior = {d:v for d,v in history.items() if d<day}
        residuals, records = replay_history(prior,day,issues)
        load, _ = load_prediction(prior,day)
        if day not in history or day-timedelta(days=1) not in prior:
            raise ValueError("Q3测试日期缺少实际观测或午夜锚点")
        observations = history[day]
        result = simulate_day(day,lambda slot: (float(observations["load"][slot-1]),float(observations["pv"][slot-1])),
                              float(prior[day-timedelta(days=1)]["pv"][-1])*6, load,price,issues,records,residuals,
                              current_soc,alpha,risk_weight)
        actual = result["actual_schedule"]
        actual["source_time"] = observations["source_time"]
        # 仅首日人工初始化，后续日严禁重置6000。
        current_soc = float(actual.soc_real_end_kwh.iloc[-1])
        outputs.append(result)
    return {key:pd.concat([result[key] for result in outputs],ignore_index=True) for key in outputs[0]}
