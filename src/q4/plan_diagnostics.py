"""Q4局部计划故障记录；不改变冻结Q3的目标、约束和SCIP设置。"""
import inspect
import json
from datetime import datetime, timezone
from pathlib import Path
from types import FunctionType
import numpy as np
from pyscipopt import Model
from src.common.data_loader import file_hash
from src.q3.optimizer import solve_plan, COST_LOCK_TOLERANCE, SOLVER_FEASTOL

SIGNATURE = inspect.signature(solve_plan)


def numeric_range(values):
    if values is None:
        return None
    array = np.asarray(values,float)
    finite = array[np.isfinite(array)]
    return dict(shape=list(array.shape),minimum=float(finite.min()) if finite.size else None,
                maximum=float(finite.max()) if finite.size else None,
                negative_count=int((array<0).sum()),nonfinite_count=int((~np.isfinite(array)).sum()))


def diagnostic_plan(*args, date, directory, solver=solve_plan, **kwargs):
    """只替换本次调用的Model构造器，成功路径返回原求解器的完整结果。"""
    bound = SIGNATURE.bind(*args,**kwargs)
    bound.apply_defaults()
    inputs = bound.arguments
    n = len(inputs['price'])
    slot = 145-n
    report = dict(date=str(date),update_time=f'{(slot-1)//6:02d}:00',slot=slot,
                  horizon_length=n,scenario_count=len(inputs['load_scenarios']),
                  start_soc=float(inputs['start_soc']),alpha=float(inputs['alpha']),
                  **{'lambda':float(inputs['risk_weight'])},primary_star=None,primary_status=None,
                  optimize_calls=0,COST_LOCK_TOLERANCE=COST_LOCK_TOLERANCE,SOLVER_FEASTOL=SOLVER_FEASTOL,
                  input_ranges={key:numeric_range(inputs[key]) for key in
                                ('price','load_scenarios','pv_scenarios','previous_plan')})
    # 精确输入在进入求解器前复制，异常后不依赖已释放的SCIP模型指针。
    arrays = {key:np.asarray(inputs[key]).copy() for key in
              ('load_scenarios','pv_scenarios','price','start_soc','alpha','risk_weight')}
    arrays['previous_plan_present'] = np.asarray(inputs['previous_plan'] is not None)
    arrays['previous_plan'] = np.asarray([] if inputs['previous_plan'] is None else inputs['previous_plan'],float).copy()
    arrays['date'] = np.asarray(str(date))
    artifact = None

    class ObservedModel(Model):
        def optimize(self):
            nonlocal artifact
            report['optimize_calls'] += 1
            stage = report['optimize_calls']
            try:
                super().optimize()
            except Exception as error:
                # 先保存NPZ/JSON，再尝试导出LP；导出失败不能覆盖原始SCIP异常。
                directory_path = Path(directory)
                directory_path.mkdir(parents=True,exist_ok=True)
                stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
                artifact = directory_path/f'plan_failure_a{inputs["alpha"]:.2f}_l{inputs["risk_weight"]:.2f}_{date}_s{slot}_{stamp}'.replace('.','p')
                report.update(error=str(error),error_type=type(error).__name__,
                              failed_stage='primary' if stage==1 else 'secondary',
                              captured_at_utc=stamp,provenance='Q4 plan exception capture')
                np.savez(artifact.with_suffix('.npz'),**arrays)
                report['npz_sha256'] = file_hash(artifact.with_suffix('.npz'))
                for extension,export in (('.cip',self.writeProblem),('.set',self.writeParams)):
                    try:
                        export(str(artifact.with_suffix(extension)))
                    except Exception as export_error:
                        report[f'{extension}_export_error'] = str(export_error)
                artifact.with_suffix('.json').write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
                raise
            if stage==1:
                report['primary_status'] = str(self.getStatus())
                if report['primary_status']=='optimal':
                    star = float(self.getObjVal())
                    report['primary_star'] = star
                    report['cost_lock'] = dict(lower=star-COST_LOCK_TOLERANCE,upper=star+COST_LOCK_TOLERANCE,
                        lower_margin_at_star=star-(star-COST_LOCK_TOLERANCE),upper_margin_at_star=star+COST_LOCK_TOLERANCE-star,
                        tolerance_over_abs_star=COST_LOCK_TOLERANCE/abs(star) if star else None)
                    # 保留一级解尺度，不在freeTransform之后读取失效的一级解。
                    for prefix in ('g_','zeta','xi_'):
                        values = [float(self.getVal(v)) for v in self.getVars() if v.name.startswith(prefix)]
                        report[f'primary_{prefix.rstrip("_")}_range'] = numeric_range(values)
                        arrays[f'primary_{prefix.rstrip("_")}'] = np.asarray(values)

    # 测试可注入同代码结构的求解器；正式入口始终使用原solve_plan。
    observed = FunctionType(solver.__code__,dict(solver.__globals__,Model=ObservedModel),argdefs=solver.__defaults__)
    try:
        return observed(*args,**kwargs)
    except Exception as error:
        if artifact is not None:
            error.add_note(f'Q4计划失败快照：{artifact}.json')
        raise


def replay_snapshot(path, repeats=1):
    """仅重放同一份NPZ中的计划LP，不运行日循环、年度引擎或搜索。"""
    if not 1<=repeats<=3:
        raise ValueError('单案例重放次数仅允许1至3')
    path = Path(path)
    saved = json.loads(path.with_suffix('.json').read_text(encoding='utf-8'))
    if file_hash(path)!=saved['npz_sha256']:
        raise ValueError('失败NPZ的SHA-256不一致')
    with np.load(path,allow_pickle=False) as data:
        args = [data[key].copy() for key in ('load_scenarios','pv_scenarios','price')]
        args += [float(data[key]) for key in ('start_soc','alpha','risk_weight')]
        args += [data['previous_plan'].copy() if bool(data['previous_plan_present']) else None]
        date = str(data['date'])
    results = []
    for index in range(repeats):
        try:
            result = diagnostic_plan(*args,date=date,directory=path.parent/'replay')
            results.append(dict(attempt=index+1,success=True,primary_star=result['primary_star'],
                primary_status=result['primary_status'],secondary_status=result['secondary_status'],
                primary_objective=result['primary_objective'],secondary_throughput=result['secondary_throughput'],
                max_violation=result['max_violation']))
        except Exception as error:
            results.append(dict(attempt=index+1,success=False,error=str(error),notes=getattr(error,'__notes__',[])))
    destination = path.parent/f'{path.stem}_replay.json'
    destination.write_text(json.dumps(dict(source=str(path),attempts=results),ensure_ascii=False,indent=2),encoding='utf-8')
    return results
