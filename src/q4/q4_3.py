"""通过价格数组适配器直接运行冻结Q3完整日循环，之后另行真实结算。"""

import numpy as np
import pandas as pd
import json
from pathlib import Path
from types import FunctionType
from src.q3.optimizer import solve_actual_step, solve_plan, VALIDATION_TOL
from src.q3.simulation import simulate_day
from src.q4.price_forecasting import PriceStream

REFERENCE_LABEL = "Q4-3 PROVISIONAL / PAPER REFERENCE ONLY; NOT FINAL Q4-3 PARAMETER"


def normalize_commitment(values):
    """只规范既有验收容差内的负尾差；先拒绝真实负值，绝不无条件截断。"""
    values = np.asarray(values,float)
    if not np.isfinite(values).all() or (values < -VALIDATION_TOL).any():
        raise ValueError(f"commitment越过既有容差：minimum={values.min()}, tolerance={VALIDATION_TOL}")
    result = values.copy()
    result[(result>=-VALIDATION_TOL)&(result<0)] = 0.
    return result


def solve_actual_tolerant(current_slot, current_actual_load, current_actual_pv,
                          load_forecast, pv_forecast, price, commitment,
                          current_soc, plan_terminal_soc, date):
    arrays = [np.asarray(a,float) for a in (load_forecast,pv_forecast,price,commitment)]
    minima = {k:float(a.min()) if a.size else None for k,a in zip(
        ("load_forecast","pv_forecast","price","commitment"),arrays)}
    try:
        # 负荷、光伏、电价仍严格非负，只有合同浮点尾差使用原VALIDATION_TOL。
        if any((a<0).any() for a in arrays[:3]):
            raise ValueError("load/PV/price必须严格非负")
        grid = normalize_commitment(arrays[3])
        return solve_actual_step(current_slot,current_actual_load,current_actual_pv,*arrays[:3],grid,
                                 current_soc,plan_terminal_soc,date)
    except ValueError as error:
        raise ValueError(f"Q4实际输入错误 date={date}, slot={current_slot}, minimum={minima}；{error}") from error


def save_negative_input(error, alpha, risk_weight, start_soc, directory):
    """仅在失败后读取原异常栈的实参，保存精确快照，不干预求解或修正数值。"""
    trace = error.__traceback__
    while trace is not None:
        if trace.tb_frame.f_code is solve_actual_step.__code__:
            values = trace.tb_frame.f_locals
            names = ("load_forecast","pv_forecast","price","commitment")
            arrays = dict(zip(names,values["arrays"]))
            report = dict(alpha=alpha,**{"lambda":risk_weight},date=str(values["date"]),
                          slot=int(values["current_slot"]),day_start_soc_kwh=float(start_soc),
                          error=str(error),inputs={})
            for name,array in arrays.items():
                negative = array[array<0]
                report["inputs"][name] = dict(minimum=float(array.min()),negative_count=len(negative),
                                              minimum_negative=float(negative.min()) if len(negative) else None)
            scalars = ("current_slot","current_actual_load","current_actual_pv","current_soc","plan_terminal_soc")
            report.update({k:float(values[k]) for k in scalars if k!="current_slot"})
            directory = Path(directory)
            directory.mkdir(parents=True,exist_ok=True)
            np.savez(directory/"last_negative_input.npz",**arrays,**{k:values[k] for k in scalars},date=str(values["date"]))
            (directory/"last_negative_input.json").write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False),encoding="utf-8")
            return report
        trace = trace.tb_next
    return None


def run_day(day, observe, midnight_pv_kw, load, baseline, issues, records, residuals,
            start_soc, alpha, risk_weight, label, stream_factory=PriceStream):
    stream = stream_factory(baseline)
    def reveal(slot):
        current_load,current_pv,current_price = observe(slot)
        stream.reveal(slot,current_price)
        return current_load,current_pv
    # 原循环在观测回调之前更新合同，因此合同只看上一slot及更早的价格。
    raw_grids = []
    def plan_boundary(*args,**kwargs):
        plan = solve_plan(*args,**kwargs)
        raw_grids.append(plan["grid"].copy())
        # 在计划输出接口统一合同表示，防止同一尾差再进入下一轮计划的严格检查。
        return dict(plan,grid=normalize_commitment(plan["grid"]))
    # 为本次调用绑定局部适配接口，不修改冻结模块全局变量；不同实验互不影响。
    adapted = FunctionType(simulate_day.__code__,dict(simulate_day.__globals__,
                           solve_plan=plan_boundary,solve_actual_step=solve_actual_tolerant),
                           argdefs=simulate_day.__defaults__)
    try:
        result = adapted(day,reveal,midnight_pv_kw,load,stream,issues,records,residuals,
                              start_soc,alpha,risk_weight,run_label=label)
    except ValueError as error:
        if str(error)!="Q3负荷、光伏、电价及承诺必须非负":
            raise ValueError(f"Q4-3 alpha={alpha}, lambda={risk_weight}, date={day}；{error}") from error
        report = save_negative_input(error,alpha,risk_weight,start_soc,
                                     Path(__file__).resolve().parents[2]/"outputs/q4/diagnostics")
        if report is None:
            raise
        raise ValueError("Q4-3负输入快照已保存："+json.dumps(report,ensure_ascii=False)) from error
    actual,plans,daily = [result[k] for k in ("actual_schedule","plan_updates","daily_metrics")]
    # 原始SCIP合同保留供独立审计，只有明确授权的负尾差被规范为0。
    plans["solver_grid_raw_kwh"] = np.concatenate(raw_grids)
    plans["commitment_roundoff_adjustment_kwh"] = plans.new_plan_kwh-plans.solver_grid_raw_kwh
    real = np.asarray(stream.observed)
    refresh = pd.DataFrame(stream.refreshes)
    refresh.insert(0,"date",str(day))
    refresh["baseline_price_yuan_per_kwh"] = baseline
    result["price_refresh"] = refresh
    plans["predicted_adjustment_cost_yuan"] = plans.adjustment_cost_yuan
    for hour in (0,6,12,18):
        mask = plans.update_time.eq(f"{hour:02d}:00")
        indices = plans.loc[mask,"slot"].to_numpy(int)-1
        gamma = 1. if hour==0 else float(refresh.gamma.iloc[hour*6-1])
        plans.loc[mask,"price_forecast_yuan_per_kwh"] = gamma*np.asarray(baseline)[indices]
        plans.loc[mask,"contract_gamma"] = gamma
        plans.loc[mask,"price_real_yuan_per_kwh"] = real[indices]
        plans.loc[mask,"adjustment_cost_yuan"] = real[indices]*(1.5*plans.loc[mask,"increase_kwh"]-.5*plans.loc[mask,"decrease_kwh"])
        key = "plan_cost_00_yuan" if hour==0 else f"adjustment_cost_{hour:02d}_yuan"
        daily[f"predicted_{key}"] = daily[key]
        daily[key] = (float(real@plans.loc[mask,"new_plan_kwh"]) if hour==0
                      else float(plans.loc[mask,"adjustment_cost_yuan"].sum()))
    # Q3实际首行价格已是真实值；初始合同及每轮u/v在执行完以后统一用真实价格结算。
    initial = plans[plans.update_time.eq("00:00")].new_plan_kwh.to_numpy()
    net_fee = plans.groupby("slot").adjustment_cost_yuan.sum().reindex(range(1,145)).to_numpy()
    actual["initial_plan_cost_real_yuan"] = real*initial
    actual["adjustment_cost_real_yuan"] = net_fee
    actual["settled_total_cost_yuan"] = real*initial+net_fee+actual.emergency_cost_slot_yuan
    daily["adjustment_cost_total_yuan"] = sum(daily[f"adjustment_cost_{h:02d}_yuan"] for h in (6,12,18))
    daily["total_actual_cost_yuan"] = daily.plan_cost_00_yuan+daily.adjustment_cost_total_yuan+daily.actual_emergency_cost_yuan
    return result
