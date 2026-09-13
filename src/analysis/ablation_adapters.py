"""局部依赖注入：只移除指定信息处理，复用冻结执行路径。"""

import ast
import inspect
import runpy
from types import FunctionType

import numpy as np

from src.q2.risk import historical_risk
from src.q3 import annual, forecast, simulation


def bind(function, **dependencies):
    # 复制函数的全局名字表，不 monkey patch 正式模块，保留原字节码和默认值。
    result = FunctionType(function.__code__, {**function.__globals__, **dependencies},
                          function.__name__, function.__defaults__, function.__closure__)
    result.__kwdefaults__ = function.__kwdefaults__
    return result


def zero_quantile(values):
    values = np.asarray(values, float)
    if values.ndim != 2 or not len(values) or not np.isfinite(values).all():
        raise ValueError("Q2-A历史残差必须为非空有限二维数组")
    return np.zeros(values.shape[1], dtype=float)


zero_risk = bind(historical_risk, empirical_quantile_type1=zero_quantile)


def q2_runner(root):
    namespace = runpy.run_path(str(root / "scripts/05_run_q2.py"))
    original = namespace["run_q2"]
    tree = ast.parse(inspect.getsource(original))
    replacements = {
        "outputs/comparison/q2_rolling_benchmark": "outputs/model_validation/q2_risk_ablation/smoke",
        "outputs/q2": "outputs/model_validation/q2_risk_ablation/run",
    }
    found = []
    # 仅改写两个输出路径常量；数学、预测、实际滚动及日循环保持原 AST。
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value in replacements:
            found.append(node.value)
            node.value = replacements[node.value]
    if set(found) != set(replacements) or len(found) != 2:
        raise RuntimeError("Q2入口结构变化，停止而非猜测输出路径")
    # 恢复原函数行号，使实验异常准确指向冻结入口，不影响执行语义。
    ast.increment_lineno(tree, original.__code__.co_firstlineno - 1)
    namespace.update(historical_risk=zero_risk, archive_expost=lambda root: None,
                     write_comparison=lambda *args: None)
    exec(compile(tree, str(root / "scripts/05_run_q2.py"), "exec"), namespace)
    return namespace["run_q2"]


def direct_confidence(*args, **kwargs):
    # 保留严格历史检查和误差诊断；实验处理仅把当次剩余预测权重设为1。
    return {**forecast.confidence(*args, **kwargs), "confidence_rho": 1.0}


direct_update = bind(forecast.update_pv, confidence=direct_confidence)
direct_replay = bind(forecast.replay_completed_day, update_pv=direct_update)
direct_history = bind(forecast.replay_history, replay_completed_day=direct_replay)
direct_simulate = bind(simulation.simulate_day, update_pv=direct_update)


class DirectCache(annual.HistoricalCache):
    # 历史实际减去本实验直接替换预测，不能复用正式融合残差。
    prepare = bind(annual.HistoricalCache.prepare, replay_completed_day=direct_replay)


run_q3_direct = bind(annual.run_dates, HistoricalCache=DirectCache, simulate_day=direct_simulate)
