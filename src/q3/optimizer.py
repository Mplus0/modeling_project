"""Q3共享购电场景计划及专用实际运行三级词典序。"""

import numpy as np
import pandas as pd
from pyscipopt import Model, quicksum

from src.q2.optimizer import (COST_LOCK_TOLERANCE, ETA_CHARGE, ETA_DISCHARGE,
                              MAX_INTERVAL_ENERGY, SOC_MIN, SOC_MAX,
                              SOLVER_FEASTOL, VALIDATION_TOL, validate_schedule)


def empirical_cvar(losses, alpha):
    losses = np.asarray(losses, float)
    if losses.ndim != 1 or not len(losses) or not np.isfinite(losses).all() or not 0 < alpha < 1:
        raise ValueError("Q3 CVaR损失或alpha不合法")
    # 离散等概率CVaR在损失值处取到最小值，保留非整尾部概率的正确权重。
    return float(min(v + np.maximum(losses-v, 0).mean()/(1-alpha) for v in losses))


def solve_plan(load_scenarios, pv_scenarios, price, start_soc, alpha, risk_weight,
               previous_plan=None):
    """只接收未执行时域；返回各场景终端SOC，不擅自聚合为实际层跟踪值。"""
    loads, pvs, prices = [np.asarray(a, float) for a in (load_scenarios, pv_scenarios, price)]
    if loads.ndim != 2 or pvs.shape != loads.shape or prices.shape != (loads.shape[1],) or not loads.size:
        raise ValueError("Q3计划场景或电价尺寸不符")
    if not np.isfinite(np.r_[loads.ravel(), pvs.ravel(), prices, start_soc, alpha, risk_weight]).all():
        raise ValueError("Q3计划输入含非有限值")
    if not 0 < alpha < 1 or risk_weight < 0 or not SOC_MIN-VALIDATION_TOL <= start_soc <= SOC_MAX+VALIDATION_TOL:
        raise ValueError("Q3计划alpha、lambda或初始SOC不合法")
    if (loads < 0).any() or (pvs < 0).any() or (prices < 0).any():
        raise ValueError("Q3场景电量及电价不得为负")
    ns, n = loads.shape
    old = None if previous_plan is None else np.asarray(previous_plan, float)
    if old is not None and (old.shape != (n,) or not np.isfinite(old).all() or (old < 0).any()):
        raise ValueError("Q3上一轮有效计划不完整")
    model = Model("q3_scenario_plan")
    model.hideOutput()
    model.setRealParam("numerics/feastol", SOLVER_FEASTOL)
    grid = [model.addVar(f"g_{i}", lb=0) for i in range(n)]
    up = [model.addVar(f"u_{i}", lb=0) for i in range(n)] if old is not None else None
    down = [model.addVar(f"v_{i}", lb=0) for i in range(n)] if old is not None else None
    if old is not None:
        for i in range(n):
            model.addCons(grid[i] == float(old[i]) + up[i] - down[i])
    variables, states, losses, throughputs = [], [], [], []
    for s in range(ns):
        vs = {v: [model.addVar(f"{v}_{s}_{i}", lb=0) for i in range(n)] for v in "xyqze"}
        x, y, q, z, e = [vs[v] for v in "xyqze"]
        soc = [model.addVar(f"S_{s}_{i}", lb=SOC_MIN, ub=SOC_MAX) for i in range(n)]
        for i in range(n):
            previous = start_soc if i == 0 else soc[i-1]
            model.addCons(soc[i] == previous + ETA_CHARGE*(x[i]+q[i]) - z[i]/ETA_DISCHARGE)
            # 全部场景共享同一购电决策，场景内部仅调整分配及紧急补偿。
            model.addCons(x[i]+y[i] == grid[i])
            model.addCons(float(pvs[s, i])-q[i]+y[i]+z[i]+e[i] >= float(loads[s, i]))
            model.addCons(q[i] <= float(pvs[s, i]))
            model.addCons(x[i]+q[i] <= MAX_INTERVAL_ENERGY)
            model.addCons(z[i] <= MAX_INTERVAL_ENERGY)
        # 计划层不添加任何终端恢复约束或终端惩罚。
        variables.append(vs)
        states.append(soc)
        losses.append(quicksum(5*float(prices[i])*e[i] for i in range(n)))
        throughputs.append(quicksum(ETA_CHARGE*(x[i]+q[i])+z[i]/ETA_DISCHARGE for i in range(n)))
    zeta = model.addVar("zeta", lb=None)
    xi = [model.addVar(f"xi_{s}", lb=0) for s in range(ns)]
    for s in range(ns):
        model.addCons(xi[s] >= losses[s]-zeta)
    cvar = zeta + quicksum(xi)/((1-alpha)*ns)
    # 调整相对于上一轮有效计划结算，减少部分的净退款为0.5倍电价。
    purchase = quicksum(float(prices[i])*(grid[i] if old is None else 1.5*up[i]-.5*down[i]) for i in range(n))
    primary = purchase + quicksum(losses)/ns + risk_weight*cvar
    throughput = quicksum(throughputs)/ns
    try:
        model.setObjective(primary, "minimize")
        model.optimize()
        first_status = str(model.getStatus())
        if first_status != "optimal":
            raise RuntimeError(f"Q3计划一级状态: {first_status}")
        star = float(model.getObjVal())
        model.freeTransform()
        model.addCons(primary <= star+COST_LOCK_TOLERANCE)
        model.addCons(primary >= star-COST_LOCK_TOLERANCE)
        model.setObjective(throughput, "minimize", clear=True)
        model.optimize()
        second_status = str(model.getStatus())
        if second_status != "optimal":
            raise RuntimeError(f"Q3计划二级状态: {second_status}")
        h_star = float(model.getObjVal())
        g = np.array([model.getVal(v) for v in grid])
        increase = np.zeros(n) if up is None else np.array([model.getVal(v) for v in up])
        decrease = np.zeros(n) if down is None else np.array([model.getVal(v) for v in down])
        zeta_value = float(model.getVal(zeta))
        xi_values = np.array([model.getVal(v) for v in xi])
        frames, checks = [], []
        for s in range(ns):
            values = {v: np.array([model.getVal(k) for k in vs]) for v, vs in variables[s].items()}
            ss = np.array([model.getVal(v) for v in states[s]])
            frame = pd.DataFrame(dict(scenario=s, slot=np.arange(1,n+1), price_yuan_per_kwh=prices,
                                       load_actual_kwh=loads[s], pv_actual_kwh=pvs[s],
                                       grid_purchase_plan_kwh=g, soc_real_start_kwh=np.r_[start_soc,ss[:-1]],
                                       soc_real_end_kwh=ss, emergency_purchase_kwh=values["e"]))
            for v in "xyqz":
                frame[f"{v}_real_kwh"] = values[v]
            frame["planned_cost_slot_yuan"] = prices*g
            frame["emergency_cost_slot_yuan"] = 5*prices*values["e"]
            frame["total_cost_slot_yuan"] = frame.planned_cost_slot_yuan+frame.emergency_cost_slot_yuan
            # 复用实际模式复核共享合同与物理约束，避免引入Q2计划模式的终端等式。
            checks.append(validate_schedule(frame, "actual", start_soc))
            frames.append(frame)
    finally:
        model.freeProb()
    costs = np.array([c["cost"] for c in checks])
    purchase_cost = float(prices @ (g if old is None else 1.5*increase-.5*decrease))
    cvar_aux = float(zeta_value+xi_values.mean()/(1-alpha))
    primary_value = purchase_cost+float(costs.mean())+risk_weight*cvar_aux
    violations = dict(primary_preservation=abs(primary_value-star),
                       throughput=abs(np.mean([c["throughput"] for c in checks])-h_star),
                       cvar_constraints=float(max(0., np.max(costs-zeta_value-xi_values), -xi_values.min())),
                       scenario_physics=max(c["max_violation"] for c in checks))
    if old is not None:
        violations["adjustment_identity"] = float(np.max(np.abs(g-old-increase+decrease)))
    if max(violations.values()) > VALIDATION_TOL:
        raise RuntimeError(f"Q3计划独立复核失败: {violations}")
    return dict(grid=g, increase=increase, decrease=decrease, scenario_schedules=frames,
                scenario_terminal_soc=[float(f.soc_real_end_kwh.iloc[-1]) for f in frames],
                primary_status=first_status, secondary_status=second_status, primary_star=star,
                primary_objective=primary_value, secondary_throughput=h_star,
                purchase_or_adjustment_cost=purchase_cost, expected_emergency_cost=float(costs.mean()),
                cvar_auxiliary=cvar_aux, cvar_empirical=empirical_cvar(costs, alpha),
                zeta=zeta_value, xi=xi_values, violations=violations,
                max_violation=max(violations.values()))


def solve_actual_step(current_slot, current_actual_load, current_actual_pv,
                      load_forecast, pv_forecast, price, commitment,
                      current_soc, plan_terminal_soc, date):
    """未来只接收预测；返回剩余时域方案，调用方只能执行第一行。"""
    arrays = [np.asarray(a, float) for a in (load_forecast, pv_forecast, price, commitment)]
    n_total = len(arrays[0])
    if not 1 <= current_slot <= n_total or any(a.shape != (n_total,) for a in arrays):
        raise ValueError("Q3滚动slot、预测或购电承诺尺寸不符")
    scalars = np.array([current_actual_load, current_actual_pv, current_soc, plan_terminal_soc], float)
    if not np.isfinite(np.concatenate(arrays + [scalars])).all():
        raise ValueError("Q3滚动输入含非有限值")
    if any((a < 0).any() for a in arrays) or min(current_actual_load, current_actual_pv) < 0:
        raise ValueError("Q3负荷、光伏、电价及承诺必须非负")
    # 加权期望及真实状态递推可能产生浮点尾差，仅按既有容差验收，绝不裁剪状态。
    if not SOC_MIN-VALIDATION_TOL <= current_soc <= SOC_MAX+VALIDATION_TOL or not SOC_MIN-VALIDATION_TOL <= plan_terminal_soc <= SOC_MAX+VALIDATION_TOL:
        raise ValueError("Q3当前SOC或最新计划终端SOC越界")
    start = current_slot - 1
    load, pv, prices, grid = [a[start:].copy() for a in arrays]
    # 只揭示当前实测，不把目标日未来真实曲线传入优化器。
    load[0], pv[0] = current_actual_load, current_actual_pv
    n = len(load)
    model = Model(f"q3_actual_{date}_{current_slot}")
    model.hideOutput()
    model.setRealParam("numerics/feastol", SOLVER_FEASTOL)
    variables = {v: [model.addVar(f"{v}_{i}", lb=0) for i in range(n)] for v in "xyqze"}
    x, y, q, z, e = [variables[v] for v in "xyqze"]
    soc = [model.addVar(f"S_{i}", lb=SOC_MIN, ub=SOC_MAX) for i in range(n)]
    gap = model.addVar("absolute_terminal_gap", lb=0)
    for i in range(n):
        previous = current_soc if i == 0 else soc[i-1]
        model.addCons(soc[i] == previous + ETA_CHARGE * (x[i] + q[i]) - z[i] / ETA_DISCHARGE)
        model.addCons(x[i] + y[i] == float(grid[i]))
        model.addCons(float(pv[i]) - q[i] + y[i] + z[i] + e[i] >= float(load[i]))
        model.addCons(q[i] <= float(pv[i]))
        model.addCons(x[i] + q[i] <= MAX_INTERVAL_ENERGY)
        model.addCons(z[i] <= MAX_INTERVAL_ENERGY)
    # 双侧约束表达绝对偏差；参考最新计划，不恢复日初或历史SOC。
    model.addCons(gap >= soc[-1] - float(plan_terminal_soc))
    model.addCons(gap >= float(plan_terminal_soc) - soc[-1])
    cost = quicksum(5 * float(prices[i]) * e[i] for i in range(n))
    throughput = quicksum(ETA_CHARGE * (x[i] + q[i]) + z[i] / ETA_DISCHARGE for i in range(n))
    stars, statuses = [], []
    try:
        for stage, objective in enumerate((cost, gap, throughput), 1):
            model.setObjective(objective, "minimize", clear=True)
            model.optimize()
            status = str(model.getStatus())
            if status != "optimal":
                raise RuntimeError(f"Q3 {date} slot{current_slot} 第{stage}级求解状态: {status}")
            stars.append(float(model.getObjVal()))
            statuses.append(status)
            if stage < 3:
                # 逐级双侧锁定；容差沿用已验证数值设置，不以加权和替代词典序。
                model.freeTransform()
                model.addCons(objective <= stars[-1] + COST_LOCK_TOLERANCE)
                model.addCons(objective >= stars[-1] - COST_LOCK_TOLERANCE)
        values = {v: np.array([model.getVal(k) for k in vs]) for v, vs in variables.items()}
        states = np.array([model.getVal(k) for k in soc])
        gap_value = float(model.getVal(gap))
    finally:
        model.freeProb()
    frame = pd.DataFrame(dict(date=str(date), slot=np.arange(current_slot, n_total+1),
                              price_yuan_per_kwh=prices, grid_purchase_plan_kwh=grid,
                              load_actual_kwh=load, pv_actual_kwh=pv,
                              soc_real_start_kwh=np.r_[current_soc, states[:-1]], soc_real_end_kwh=states,
                              plan_terminal_soc_kwh=float(plan_terminal_soc)))
    for v in "xyqz":
        frame[f"{v}_real_kwh"] = values[v]
    frame["emergency_purchase_kwh"] = values["e"]
    frame["planned_cost_slot_yuan"] = prices * grid
    frame["emergency_cost_slot_yuan"] = 5 * prices * values["e"]
    # 该列只服务物理调度复核；Q3最终结算必须另计初始购电及各轮调整费用。
    frame["total_cost_slot_yuan"] = frame.planned_cost_slot_yuan + frame.emergency_cost_slot_yuan
    checked = validate_schedule(frame, "actual", current_soc, stars[0], stars[2])
    true_gap = abs(float(states[-1]) - plan_terminal_soc)
    checked["violations"].update(absolute_gap_constraint=max(0., true_gap-gap_value),
                                  absolute_gap_preservation=abs(true_gap-stars[1]),
                                  gap_auxiliary_preservation=abs(gap_value-stars[1]))
    checked["max_violation"] = max(checked["violations"].values())
    checked.update(primary_star=stars[0], terminal_gap_star=stars[1], terminal_gap=true_gap,
                   tertiary_objective=stars[2], primary_status=statuses[0],
                   secondary_status=statuses[1], tertiary_status=statuses[2])
    if checked["max_violation"] > VALIDATION_TOL:
        raise RuntimeError(f"Q3实际运行独立复核失败: {checked['violations']}")
    return frame, checked
