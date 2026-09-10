"""严格按已确认的连续线性规划求解 Q1，不修改输入数据。"""

from pathlib import Path

import numpy as np
import pandas as pd
from pyscipopt import Model, quicksum

from src.common.time_utils import clock_seconds

ETA_CHARGE = 0.90
ETA_DISCHARGE = 0.90
INITIAL_SOC = 6000.0
SOC_MIN = 1200.0
SOC_MAX = 10800.0
MAX_INTERVAL_ENERGY = 5000 * 10 / 60
SOLVER_FEASTOL = 1e-9
VALIDATION_TOL = 1e-6
INPUT_COLUMNS = ["slot", "source_time", "price_yuan_per_kwh", "load_kw", "pv_forecast_kw",
                 "load_kwh", "pv_forecast_kwh"]


def load_input(path):
    frame = pd.read_csv(Path(path), float_precision="round_trip", keep_default_na=False)
    validate_input(frame)
    return frame


def validate_input(frame):
    if list(frame.columns) != INPUT_COLUMNS or len(frame) != 144:
        raise ValueError("Q1 输入必须为规定的 7 列和 144 行")
    if frame["slot"].tolist() != list(range(1, 145)):
        raise ValueError("Q1 slot 必须按顺序为 1..144")
    if [clock_seconds(v) for v in frame["source_time"]] != list(range(600, 86401, 600)):
        raise ValueError("Q1 原始时间标签不完整或顺序不符")
    for column in INPUT_COLUMNS[2:]:
        if not pd.api.types.is_numeric_dtype(frame[column]) or not np.isfinite(frame[column]).all():
            raise ValueError(f"Q1 {column} 含缺失或非有限数值")
    for power, energy in [("load_kw", "load_kwh"), ("pv_forecast_kw", "pv_forecast_kwh")]:
        if not np.allclose(frame[power] * (10 / 60), frame[energy], rtol=0, atol=1e-9):
            raise ValueError(f"Q1 {energy} 与 10 分钟换算不符")


def evaluate_schedule(schedule, c_star, secondary_objective):
    """只用导出的逐时段数值重新计算约束，不依赖求解器可行性标记。"""
    validate_input(schedule[INPUT_COLUMNS])
    if not np.isfinite(schedule.select_dtypes(include="number").to_numpy()).all():
        raise ValueError("Q1 调度含非有限数值")
    x, y, q, z, soc = (schedule[c].to_numpy(float) for c in ("x_kwh", "y_kwh", "q_kwh", "z_kwh", "soc_kwh"))
    previous = np.r_[INITIAL_SOC, soc[:-1]]
    charge, release = ETA_CHARGE * (x + q), z / ETA_DISCHARGE
    load, pv, price = (schedule[c].to_numpy(float) for c in ("load_kwh", "pv_forecast_kwh", "price_yuan_per_kwh"))
    cost = float(np.dot(price, x + y))
    throughput = float(np.sum(charge + release))
    def positive_max(values):
        return float(max(0.0, np.max(values)))
    violations = {
        "nonnegative_kwh": positive_max(-np.r_[x, y, q, z]),
        "soc_balance_kwh": float(np.max(np.abs(soc - previous - charge + release))),
        "soc_bounds_kwh": positive_max(np.r_[SOC_MIN - soc, soc - SOC_MAX]),
        "initial_soc_kwh": abs(float(schedule["soc_previous_kwh"].iloc[0]) - INITIAL_SOC),
        "final_soc_kwh": abs(float(soc[-1]) - INITIAL_SOC),
        "pv_allocation_kwh": positive_max(q - pv),
        "charge_limit_kwh": positive_max(x + q - MAX_INTERVAL_ENERGY),
        "discharge_limit_kwh": positive_max(z - MAX_INTERVAL_ENERGY),
        "supply_balance_kwh": positive_max(load - (pv - q + y + z)),
        "primary_cost_difference_yuan": abs(cost - c_star),
        "secondary_objective_difference_kwh": abs(throughput - secondary_objective),
    }
    derived = {"soc_previous_kwh": previous, "grid_purchase_kwh": x + y,
               "charge_input_kwh": x + q, "battery_charge_kwh": charge,
               "battery_discharge_kwh": release, "supply_surplus_kwh": pv - q + y + z - load,
               "cost_yuan": price * (x + y), "throughput_kwh": charge + release}
    violations["derived_columns_max_error"] = max(float(np.max(np.abs(schedule[k].to_numpy(float) - v)))
                                                 for k, v in derived.items())
    all_soc = np.r_[INITIAL_SOC, soc]
    return {
        "primary_cost": cost, "C_star": float(c_star), "total_grid_purchase": float(np.sum(x + y)),
        "secondary_throughput": throughput, "initial_soc": INITIAL_SOC, "final_soc": float(soc[-1]),
        "min_soc": float(all_soc.min()), "max_soc": float(all_soc.max()),
        "maximum_supply_balance_violation": violations["supply_balance_kwh"],
        "maximum_soc_violation": violations["soc_bounds_kwh"],
        # 容差只用于判断数值残差和统计同充同放，不裁剪求解器变量。
        "simultaneous_charge_discharge_intervals": int(np.sum((x + q > VALIDATION_TOL) & (z > VALIDATION_TOL))),
        "violations": violations, "validation_tolerance": VALIDATION_TOL,
        "validation_passed": all(v <= VALIDATION_TOL for v in violations.values()),
    }


def solve_q1(frame):
    validate_input(frame)
    model = Model("q1_lexicographic_lp")
    model.hideOutput()
    model.setRealParam("numerics/feastol", SOLVER_FEASTOL)
    x, y, q, z = [[model.addVar(f"{name}_{i+1}", lb=0, vtype="C") for i in range(144)]
                   for name in ("x", "y", "q", "z")]
    soc = [model.addVar(f"S_{i+1}", lb=SOC_MIN, ub=SOC_MAX) for i in range(144)]
    price = frame["price_yuan_per_kwh"].to_numpy(float)
    load = frame["load_kwh"].to_numpy(float)
    pv = frame["pv_forecast_kwh"].to_numpy(float)
    for i in range(144):
        previous = INITIAL_SOC if i == 0 else soc[i-1]
        # x、q 为充电端输入，z 为实际送达负载的电量；SOC 按电池内部效率记账。
        model.addCons(soc[i] == previous + ETA_CHARGE * (x[i] + q[i]) - z[i] / ETA_DISCHARGE)
        model.addCons(pv[i] - q[i] + y[i] + z[i] >= load[i])
        model.addCons(q[i] <= pv[i])
        model.addCons(x[i] + q[i] <= MAX_INTERVAL_ENERGY)
        model.addCons(z[i] <= MAX_INTERVAL_ENERGY)
    model.addCons(soc[-1] == INITIAL_SOC)
    cost = quicksum(float(price[i]) * (x[i] + y[i]) for i in range(144))
    throughput = quicksum(ETA_CHARGE * (x[i] + q[i]) + z[i] / ETA_DISCHARGE for i in range(144))
    model.setObjective(cost, "minimize")
    model.optimize()
    primary_status = str(model.getStatus())
    if primary_status != "optimal":
        raise RuntimeError(f"Q1 一级求解未达到最优：{primary_status}")
    c_star = float(model.getObjVal())
    primary_recomputed = sum(price[i] * (model.getVal(x[i]) + model.getVal(y[i])) for i in range(144))
    if abs(primary_recomputed - c_star) > VALIDATION_TOL:
        raise RuntimeError("Q1 一级目标重算不一致")
    # 保留原约束，将费用锁定为一级最优值；等式允许的偏差仅来自求解器数值容差。
    model.freeTransform()
    model.addCons(cost == c_star, name="primary_optimal_cost_lock")
    model.setObjective(throughput, "minimize", clear=True)
    model.optimize()
    secondary_status = str(model.getStatus())
    if secondary_status != "optimal":
        raise RuntimeError(f"Q1 二级求解未达到最优：{secondary_status}")
    secondary_objective = float(model.getObjVal())
    schedule = frame.copy(deep=True)
    for name, variables in [("x_kwh", x), ("y_kwh", y), ("q_kwh", q), ("z_kwh", z), ("soc_kwh", soc)]:
        schedule[name] = [model.getVal(v) for v in variables]
    schedule["soc_previous_kwh"] = np.r_[INITIAL_SOC, schedule["soc_kwh"].to_numpy()[:-1]]
    schedule["grid_purchase_kwh"] = schedule["x_kwh"] + schedule["y_kwh"]
    schedule["charge_input_kwh"] = schedule["x_kwh"] + schedule["q_kwh"]
    schedule["battery_charge_kwh"] = ETA_CHARGE * schedule["charge_input_kwh"]
    schedule["battery_discharge_kwh"] = schedule["z_kwh"] / ETA_DISCHARGE
    schedule["supply_surplus_kwh"] = schedule["pv_forecast_kwh"] - schedule["q_kwh"] + schedule["y_kwh"] + schedule["z_kwh"] - schedule["load_kwh"]
    schedule["cost_yuan"] = schedule["price_yuan_per_kwh"] * schedule["grid_purchase_kwh"]
    schedule["throughput_kwh"] = schedule["battery_charge_kwh"] + schedule["battery_discharge_kwh"]
    metrics = evaluate_schedule(schedule, c_star, secondary_objective)
    metrics.update({"primary_status": primary_status, "secondary_status": secondary_status,
                    "primary_solver_objective": c_star, "primary_recomputed_objective": float(primary_recomputed),
                    "secondary_solver_objective": secondary_objective, "solver_feasibility_tolerance": SOLVER_FEASTOL,
                    "cost_lock": "equality to C_star", "parameters": {
                        "eta_charge": ETA_CHARGE, "eta_discharge": ETA_DISCHARGE, "initial_soc_kwh": INITIAL_SOC,
                        "soc_min_kwh": SOC_MIN, "soc_max_kwh": SOC_MAX, "max_interval_energy_kwh": MAX_INTERVAL_ENERGY}})
    return schedule, metrics
