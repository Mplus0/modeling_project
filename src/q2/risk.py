"""逐 slot 的 Type-1 经验分位数，保留负风险修正。"""

import math
import numpy as np


def empirical_quantile_type1(values, tau=0.8):
    values = np.asarray(values, dtype=float)
    if values.ndim not in (1, 2) or len(values) == 0 or not np.isfinite(values).all():
        raise ValueError("经验分位数需要非空、有限的历史样本")
    if not 0 < tau <= 1:
        raise ValueError("经验分位数 tau 必须位于 (0,1]")
    # 逆经验CDF取第 ceil(tau*n) 个顺序统计量，不作线性插值或负值截断。
    return np.sort(values, axis=0)[math.ceil(tau * len(values)) - 1]


def historical_risk(residuals, target):
    dates = sorted(residuals)
    if not dates:
        raise ValueError(f"{target} 无可用历史残差，不得伪造风险样本")
    if any(day >= target for day in dates):
        raise ValueError("风险样本包含目标日或未来残差")
    return empirical_quantile_type1([residuals[d] for d in dates]), dates
