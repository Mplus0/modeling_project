"""因果滚动运行：当前观测＋冻结预测，只执行当前一步。"""

from time import perf_counter

import numpy as np
import pandas as pd
from pyscipopt import Model, quicksum

from src.q2.optimizer import (COST_LOCK_TOLERANCE, ETA_CHARGE, ETA_DISCHARGE,
                              MAX_INTERVAL_ENERGY, SOC_MIN, SOC_MAX,
                              SOLVER_FEASTOL, VALIDATION_TOL, validate_schedule)

# 仅用于锁定二级最优缺口的浮点数值稳定性，不是经济权重或新模型参数。
TERMINAL_GAP_LOCK_TOLERANCE = 1e-7


def solve_actual_rolling_step(current_slot, current_actual_load, current_actual_pv,
                              load_forecast, pv_forecast, price, frozen_commitment,
                              current_soc, day_start_soc, date):
    """不接收未来真实数组；返回剩余时域诊断方案，调用方只能执行第一行。"""
    arrays = [np.asarray(a, float) for a in (load_forecast, pv_forecast, price, frozen_commitment)]
    total = len(arrays[0])
    if not 1 <= current_slot <= total or any(a.shape != (total,) for a in arrays):
        raise ValueError("滚动slot或冻结预测/承诺尺寸不符")
    if not np.isfinite(np.concatenate(arrays + [np.array([current_actual_load, current_actual_pv, current_soc, day_start_soc])])).all():
        raise ValueError("滚动输入含非有限值")
    start = current_slot - 1
    load, pv, prices, commitment = [a[start:].copy() for a in arrays]
    # 丢弃过去，只用当前真实观测覆盖首项，所有未来项保留0:00预测。
    load[0], pv[0] = current_actual_load, current_actual_pv
    n = len(load)
    model = Model(f"q2_rolling_{date}_{current_slot}")
    model.hideOutput()
    model.setRealParam("numerics/feastol", SOLVER_FEASTOL)
    variables = {v: [model.addVar(f"{v}_{i}", lb=0) for i in range(n)] for v in "xyqze"}
    x, y, q, z, e = [variables[v] for v in "xyqze"]
    soc = [model.addVar(f"S_{i}", lb=SOC_MIN, ub=SOC_MAX) for i in range(n)]
    delta = model.addVar("terminal_gap", lb=0)
    for i in range(n):
        previous = current_soc if i == 0 else soc[i - 1]
        model.addCons(soc[i] == previous + ETA_CHARGE * (x[i] + q[i]) - z[i] / ETA_DISCHARGE)
        model.addCons(x[i] + y[i] == float(commitment[i]))
        model.addCons(float(load[i]) <= float(pv[i]) - q[i] + y[i] + z[i] + e[i])
        model.addCons(q[i] <= float(pv[i]))
        model.addCons(x[i] + q[i] <= MAX_INTERVAL_ENERGY)
        model.addCons(z[i] <= MAX_INTERVAL_ENERGY)
    # 参考当天固定日初真实SOC，允许超过参考值，不强制恢复或取绝对缺口。
    model.addCons(soc[-1] + delta >= day_start_soc)
    cost = quicksum(5 * float(prices[i]) * e[i] for i in range(n))
    throughput = quicksum(ETA_CHARGE * (x[i] + q[i]) + z[i] / ETA_DISCHARGE for i in range(n))
    elapsed = 0.0

    def optimize(objective, stage):
        nonlocal elapsed
        model.setObjective(objective, "minimize", clear=True)
        tick = perf_counter()
        try:
            model.optimize()
        except Exception as exc:
            raise RuntimeError(f"{date} slot {current_slot} {stage} 数值求解失败") from exc
        elapsed += perf_counter() - tick
        status = str(model.getStatus())
        if status != "optimal":
            raise RuntimeError(f"{date} slot {current_slot} {stage}: {status}")
        return float(model.getObjVal()), status

    try:
        primary_star, primary_status = optimize(cost, "primary")
        model.freeTransform()
        model.addCons(cost <= primary_star + COST_LOCK_TOLERANCE)
        model.addCons(cost >= primary_star - COST_LOCK_TOLERANCE)
        gap_star, secondary_status = optimize(delta, "secondary")
        model.freeTransform()
        model.addCons(delta <= gap_star + TERMINAL_GAP_LOCK_TOLERANCE)
        model.addCons(delta >= gap_star - TERMINAL_GAP_LOCK_TOLERANCE)
        h_star, tertiary_status = optimize(throughput, "tertiary")
        values = {v: np.array([model.getVal(k) for k in variables[v]]) for v in variables}
        states = np.array([model.getVal(k) for k in soc])
        gap = float(model.getVal(delta))
    finally:
        model.freeProb()
    frame = pd.DataFrame({"date": str(date), "slot": np.arange(current_slot, total + 1),
                          "price_yuan_per_kwh": prices, "grid_purchase_plan_kwh": commitment,
                          "load_actual_kwh": load, "pv_actual_kwh": pv,
                          "soc_day_start_kwh": day_start_soc,
                          "soc_real_start_kwh": np.r_[current_soc, states[:-1]], "soc_real_end_kwh": states})
    for v in "xyqz":
        frame[f"{v}_real_kwh"] = values[v]
    frame["emergency_purchase_kwh"] = values["e"]
    frame["planned_cost_slot_yuan"] = prices * commitment
    frame["emergency_cost_slot_yuan"] = 5 * prices * values["e"]
    frame["total_cost_slot_yuan"] = frame.planned_cost_slot_yuan + frame.emergency_cost_slot_yuan
    checked = validate_schedule(frame, "actual", current_soc, primary_star, h_star)
    checked["violations"].update(terminal_gap_nonnegative=max(0., -gap),
                                 terminal_gap_constraint=max(0., day_start_soc - states[-1] - gap),
                                 terminal_gap_preservation=abs(gap - gap_star))
    checked["max_violation"] = max(checked["violations"].values())
    checked.update(primary_star=primary_star, terminal_gap_star=gap_star, terminal_gap=gap,
                   tertiary_objective=h_star, primary_status=primary_status, secondary_status=secondary_status,
                   tertiary_status=tertiary_status, optimize_seconds=elapsed)
    if checked["max_violation"] > VALIDATION_TOL:
        raise RuntimeError(f"{date} slot {current_slot} 滚动复核失败：{checked['violations']}")
    return frame, checked


def solve_actual_rolling_day(observe_current, load_forecast, pv_forecast, price,
                             commitment, start_soc, date):
    """observe_current(slot)每次仅返回两个当前真实标量，不向求解器暴露未来轨迹。"""
    tick = perf_counter()
    frozen = [np.array(a, dtype=float, copy=True) for a in (load_forecast, pv_forecast, price, commitment)]
    for a in frozen:
        a.setflags(write=False)
    current_soc = float(start_soc)
    rows, seconds = [], 0.0
    for slot in range(1, len(frozen[0]) + 1):
        current_load, current_pv = observe_current(slot)
        horizon, check = solve_actual_rolling_step(slot, current_load, current_pv, *frozen,
                                                   current_soc, start_soc, date)
        row = horizon.iloc[0].to_dict()
        # 真正执行只取当前动作，并从实际动作重算SOC，不继承未来预测状态。
        row["soc_real_end_kwh"] = current_soc + ETA_CHARGE * (row["x_real_kwh"] + row["q_real_kwh"]) - row["z_real_kwh"] / ETA_DISCHARGE
        current_soc = row["soc_real_end_kwh"]
        row.update(load_forecast_kwh=float(frozen[0][slot-1]), pv_forecast_kwh=float(frozen[1][slot-1]),
                   rolling_horizon_length=len(horizon), rolling_primary_star_yuan=check["primary_star"],
                   rolling_terminal_gap_star_kwh=check["terminal_gap_star"],
                   rolling_terminal_gap_kwh=check["terminal_gap"],
                   rolling_tertiary_throughput_star_kwh=check["tertiary_objective"],
                   rolling_primary_status=check["primary_status"], rolling_secondary_status=check["secondary_status"],
                   rolling_tertiary_status=check["tertiary_status"], rolling_max_constraint_violation=check["max_violation"])
        row.update({f"rolling_violation_{k}": v for k, v in check["violations"].items()})
        rows.append(row)
        seconds += check["optimize_seconds"]
    actual = pd.DataFrame(rows)
    checked = validate_schedule(actual, "actual", start_soc)
    if checked["max_violation"] > VALIDATION_TOL:
        raise RuntimeError(f"{date} 实际执行约束复核失败：{checked['violations']}")
    checked.update(optimize_seconds=seconds, elapsed_seconds=perf_counter()-tick,
                   max_rolling_violation=float(actual.rolling_max_constraint_violation.max()))
    return actual, checked
