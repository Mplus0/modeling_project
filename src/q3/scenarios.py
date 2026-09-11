"""同日成对历史残差构造等概率场景，严格排除目标日和未来。"""

import numpy as np

W_S = 14


def build_scenarios(target, version, load_forecast, pv_forecast, residuals, first_slot=1):
    dates = sorted(residuals)
    if not dates or any(day >= target for day in dates):
        raise ValueError("场景需要目标日之前的合法历史残差，不能含目标日或未来")
    selected = dates[-W_S:]
    load, pv = np.asarray(load_forecast, float), np.asarray(pv_forecast, float)
    if load.shape != pv.shape or load.ndim != 1 or not 1 <= first_slot <= len(load):
        raise ValueError("场景预测尺寸或起始slot不符")
    loads, pvs = [], []
    for day in selected:
        pair = residuals[day]
        load_error = np.asarray(pair["load"], float)
        pv_error = np.asarray(pair["pv"][version], float)
        if load_error.shape != load.shape or pv_error.shape != pv.shape:
            raise ValueError(f"{day}的成对历史残差不完整")
        # 《第三问(6)》明确要求场景取max(0,预测+残差)，仅作用于场景副本。
        loads.append(np.maximum(0., load + load_error)[first_slot-1:])
        pvs.append(np.maximum(0., pv + pv_error)[first_slot-1:])
    loads, pvs = np.asarray(loads), np.asarray(pvs)
    if not np.isfinite(loads).all() or not np.isfinite(pvs).all():
        raise ValueError("联合场景含非有限值")
    return {"dates": selected, "load": loads, "pv": pvs,
            "probability": np.full(len(selected), 1/len(selected))}
