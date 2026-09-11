"""仅用目标日之前的历史有效光伏时段评价新旧版本。"""

import numpy as np

W_C = 7
EPSILON = 1e-8  # 仅防除零，固定数值稳定常量，不参与调参。


def confidence(target, update_hour, history, epsilon=EPSILON):
    """history[day]包含 actual、old、new 三条144点电量曲线。

    old必须由历史同一融合机制回放得到，不能以旧原始预报替代。
    """
    if update_hour not in (6, 12, 18) or not np.isfinite(epsilon) or epsilon <= 0:
        raise ValueError("Q3可信度更新时间或epsilon不合法")
    dates = sorted(history)
    if any(day >= target for day in dates):
        raise ValueError("Q3可信度禁止使用目标日及未来数据")
    dates = dates[-W_C:]
    result = dict(sample_count=len(dates), dates=dates, effective_slots=0,
                  historical_error_old=0., historical_error_new=0.)
    if not dates:
        return dict(result, confidence_rho=0.5)
    old_error, new_error, energy = 0., 0., 0.
    for day in dates:
        actual, old, new = [np.asarray(history[day][key], float) for key in ("actual", "old", "new")]
        if any(a.shape != (144,) for a in (actual, old, new)) or not np.isfinite(np.r_[actual, old, new]).all():
            raise ValueError(f"{day} Q3可信度历史曲线不完整")
        # slot36/72/108已执行，只评价更新时间之后且历史实际光伏严格为正的时段。
        mask = (np.arange(144) >= update_hour * 6) & (actual > 0)
        result["effective_slots"] += int(mask.sum())
        old_error += float(np.abs(old[mask] - actual[mask]).sum())
        new_error += float(np.abs(new[mask] - actual[mask]).sum())
        energy += float(actual[mask].sum())
    if not result["effective_slots"]:
        return dict(result, confidence_rho=0.)
    old_error, new_error = old_error / (energy + epsilon), new_error / (energy + epsilon)
    # 新版本误差越小，赋予新版本的权重越高；epsilon只用于已确认的数值稳定项。
    return dict(result, historical_error_old=old_error, historical_error_new=new_error,
                confidence_rho=(old_error + epsilon) / (new_error + old_error + 2 * epsilon))
