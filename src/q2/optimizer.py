"""Q2 日前计划LP与通用约束复核；旧实际LP仅保留供历史诊断。"""

import numpy as np
import pandas as pd
from pyscipopt import Model, quicksum

from src.q1.optimizer import ETA_CHARGE, ETA_DISCHARGE, INITIAL_SOC, MAX_INTERVAL_ENERGY, SOC_MAX, SOC_MIN, SOLVER_FEASTOL, VALIDATION_TOL

COST_LOCK_TOLERANCE = 1e-7


def validate_schedule(frame, mode, start_soc, primary_star=None, secondary_objective=None):
    prefix = "plan" if mode == "plan" else "real"
    x, y, q, z = [frame[f"{v}_{prefix}_kwh"].to_numpy(float) for v in "xyqz"]
    soc = frame[f"soc_{prefix}_end_kwh"].to_numpy(float)
    previous = np.r_[start_soc, soc[:-1]]
    pv = frame["pv_forecast_kwh" if mode == "plan" else "pv_actual_kwh"].to_numpy(float)
    demand = (frame.risk_adjusted_net_load_kwh.to_numpy(float) if mode == "plan"
              else (frame.load_actual_kwh - frame.pv_actual_kwh).to_numpy(float))
    emergency = np.zeros(len(frame)) if mode == "plan" else frame.emergency_purchase_kwh.to_numpy(float)
    price = frame.price_yuan_per_kwh.to_numpy(float)
    if not np.isfinite(np.r_[x, y, q, z, soc, previous, pv, demand, emergency, price]).all():
        raise ValueError("Q2 调度含非有限值")
    positive = lambda a: float(max(0, np.max(a)))
    cost = float(np.dot(price, x + y) if mode == "plan" else 5 * np.dot(price, emergency))
    throughput = float(np.sum(ETA_CHARGE * (x + q) + z / ETA_DISCHARGE))
    violations = {
        "nonnegative": positive(-np.r_[x, y, q, z, emergency]),
        "soc_bounds": positive(np.r_[SOC_MIN - soc, soc - SOC_MAX, SOC_MIN - start_soc, start_soc - SOC_MAX]),
        "soc_recursion": float(np.max(np.abs(soc - previous - ETA_CHARGE * (x + q) + z / ETA_DISCHARGE))),
        "soc_start_alignment": float(np.max(np.abs(frame[f"soc_{prefix}_start_kwh"] - previous))),
        "pv_allocation": positive(q - pv), "charge_limit": positive(x + q - MAX_INTERVAL_ENERGY),
        "discharge_limit": positive(z - MAX_INTERVAL_ENERGY),
        "supply": positive(demand - (y + z - q + emergency)),
    }
    # 实际执行序列不是某轮剩余时域最优解，不能与重叠滚动目标值比较。
    if primary_star is not None:
        violations["primary_cost_preservation"] = abs(cost - primary_star)
    if secondary_objective is not None:
        violations["secondary_objective"] = abs(throughput - secondary_objective)
    violations["terminal_soc" if mode == "plan" else "fixed_grid_purchase"] = (
        abs(float(soc[-1]) - start_soc) if mode == "plan" else float(np.max(np.abs(x + y - frame.grid_purchase_plan_kwh))))
    planned_slots = price * frame.grid_purchase_plan_kwh.to_numpy(float)
    violations["planned_cost_column"] = float(np.max(np.abs(frame.planned_cost_slot_yuan - planned_slots)))
    if mode == "actual":
        violations["emergency_cost_column"] = float(np.max(np.abs(frame.emergency_cost_slot_yuan - 5 * price * emergency)))
        violations["total_cost_column"] = float(np.max(np.abs(frame.total_cost_slot_yuan - planned_slots - 5 * price * emergency)))
    else:
        violations["grid_purchase_column"] = float(np.max(np.abs(frame.grid_purchase_plan_kwh - x - y)))
    return {"cost": cost, "throughput": throughput, "violations": violations,
            "max_violation": max(violations.values()),
            "simultaneous_slots": int(np.sum((x + q > VALIDATION_TOL) & (z > VALIDATION_TOL)))}


def _solve(mode, demand, pv, price, start_soc, date, commitment=None):
    demand, pv, price = [np.asarray(a, float) for a in (demand, pv, price)]
    n = len(price)
    if n == 0 or demand.shape != (n,) or pv.shape != (n,) or not np.isfinite(np.r_[demand, pv, price, start_soc]).all():
        raise ValueError("Q2 优化输入尺寸或数值不符")
    if commitment is not None:
        commitment = np.asarray(commitment, float).copy()
        if commitment.shape != (n,) or not np.isfinite(commitment).all():
            raise ValueError("Q2 固定购电承诺不完整")
    model = Model(f"q2_{mode}_{date}")
    model.hideOutput()
    model.setRealParam("numerics/feastol", SOLVER_FEASTOL)
    variables = {v: [model.addVar(f"{v}_{i}", lb=0, vtype="C") for i in range(n)] for v in "xyqz"}
    x, y, q, z = [variables[v] for v in "xyqz"]
    soc = [model.addVar(f"S_{i}", lb=SOC_MIN, ub=SOC_MAX) for i in range(n)]
    e = [model.addVar(f"e_{i}", lb=0, vtype="C") for i in range(n)] if mode == "actual" else [0] * n
    for i in range(n):
        previous = start_soc if i == 0 else soc[i - 1]
        model.addCons(soc[i] == previous + ETA_CHARGE * (x[i] + q[i]) - z[i] / ETA_DISCHARGE)
        model.addCons(y[i] + z[i] - q[i] + e[i] >= float(demand[i]))
        model.addCons(q[i] <= float(pv[i]))
        model.addCons(x[i] + q[i] <= MAX_INTERVAL_ENERGY)
        model.addCons(z[i] <= MAX_INTERVAL_ENERGY)
        if mode == "actual":
            # 实际运行仅重新分配已购电量，新增缺口只能由紧急购电 e 弥补。
            model.addCons(x[i] + y[i] == float(commitment[i]))
    if mode == "plan":
        model.addCons(soc[-1] == start_soc)
    # 实际运行无终端SOC等式或惩罚；日末真实状态直接传入次日。
    primary = quicksum(float(price[i]) * (x[i] + y[i] if mode == "plan" else 5 * e[i]) for i in range(n))
    throughput = quicksum(ETA_CHARGE * (x[i] + q[i]) + z[i] / ETA_DISCHARGE for i in range(n))
    model.setObjective(primary, "minimize")
    try:
        model.optimize()
    except Exception as exc:
        raise RuntimeError(f"{date} {mode} 一级LP数值求解失败") from exc
    first_status = str(model.getStatus())
    if first_status != "optimal":
        raise RuntimeError(f"{date} {mode} 一级状态 {first_status}")
    star = float(model.getObjVal())
    recomputed = sum(float(price[i]) * (model.getVal(x[i]) + model.getVal(y[i]) if mode == "plan" else 5 * model.getVal(e[i])) for i in range(n))
    if abs(star - recomputed) > VALIDATION_TOL:
        raise RuntimeError(f"{date} {mode} 一级费用复算失败")
    model.freeTransform()
    # 按已确认的数值容差锁定一级费用，避免精确浮点等式导致退化LP数值故障。
    # 1e-7元小于独立验收容差1e-6元，不引入经济性与吞吐量的加权折中。
    model.addCons(primary <= star + COST_LOCK_TOLERANCE, name="cost_lock_upper")
    model.addCons(primary >= star - COST_LOCK_TOLERANCE, name="cost_lock_lower")
    model.setObjective(throughput, "minimize", clear=True)
    try:
        model.optimize()
    except Exception as exc:
        raise RuntimeError(f"{date} {mode} 二级LP数值求解失败") from exc
    second_status = str(model.getStatus())
    if second_status != "optimal":
        raise RuntimeError(f"{date} {mode} 二级状态 {second_status}")
    second = float(model.getObjVal())
    prefix = "plan" if mode == "plan" else "real"
    frame = pd.DataFrame({"date": str(date), "slot": np.arange(1, n + 1), "price_yuan_per_kwh": price,
                          "soc_day_start_kwh": start_soc})
    for name, values in variables.items():
        frame[f"{name}_{prefix}_kwh"] = [model.getVal(v) for v in values]
    frame[f"soc_{prefix}_end_kwh"] = [model.getVal(v) for v in soc]
    frame[f"soc_{prefix}_start_kwh"] = np.r_[start_soc, frame[f"soc_{prefix}_end_kwh"].to_numpy()[:-1]]
    if mode == "plan":
        frame["grid_purchase_plan_kwh"] = frame.x_plan_kwh + frame.y_plan_kwh
        frame["pv_forecast_kwh"] = pv
        frame["risk_adjusted_net_load_kwh"] = demand
    else:
        frame["grid_purchase_plan_kwh"] = commitment
        frame["load_actual_kwh"] = demand + pv
        frame["pv_actual_kwh"] = pv
        frame["emergency_purchase_kwh"] = [model.getVal(v) for v in e]
        frame["emergency_cost_slot_yuan"] = 5 * price * frame.emergency_purchase_kwh
    frame["planned_cost_slot_yuan"] = price * frame.grid_purchase_plan_kwh
    if mode == "actual":
        frame["total_cost_slot_yuan"] = frame.planned_cost_slot_yuan + frame.emergency_cost_slot_yuan
    checked = validate_schedule(frame, mode, start_soc, star, second)
    checked.update(primary_star=star, primary_recomputed=recomputed, secondary_objective=second,
                   primary_status=first_status, secondary_status=second_status)
    if checked["max_violation"] > VALIDATION_TOL:
        raise RuntimeError(f"{date} {mode} 独立验证失败: {checked['violations']}")
    model.freeProb()
    return frame, checked


def solve_plan(net_risk, pv_forecast, price, start_soc, date):
    return _solve("plan", net_risk, pv_forecast, price, start_soc, date)


def solve_actual_expost_legacy(load_actual, pv_actual, price, start_soc, commitment, date):
    """仅供旧版诊断，正式运行禁止调用此完美预见接口。"""
    frame, checked = _solve("actual", np.asarray(load_actual) - pv_actual, pv_actual, price, start_soc, date, commitment)
    # CSV保留实际负荷原值，不用减后再加造成的浮点往返值替代。
    frame["load_actual_kwh"] = np.asarray(load_actual).copy()
    return frame, checked
