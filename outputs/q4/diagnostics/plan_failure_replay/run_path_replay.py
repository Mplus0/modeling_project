"""单组真实路径诊断：只读正式输入，首次异常即停，不写搜索/正式输出。"""
import inspect
import json
import sys
import traceback
from pathlib import Path
from time import perf_counter
from types import FunctionType
import numpy as np

ROOT = Path(__file__).resolve().parents[4]
DEST = Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
from src.common.data_loader import file_hash
from src.q3.simulation import simulate_day
from src.q3.annual import FORMAL_DATES
from src.q4.annual import run_dates
from src.q4.inputs import load_inputs, protect, frozen_hashes
from src.q4.q4_3 import run_day, save_negative_input
from src.q4.plan_diagnostics import diagnostic_plan, SIGNATURE


def write_json(name, value):
    (DEST/name).write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')


def hashes():
    # 诊断目录之外的输入、代码、搜索记录及全部结果同时保护；新增/删除也会被识别。
    return {str(p.relative_to(ROOT)):file_hash(p)
            for directory in ('data','src','scripts','outputs') for p in (ROOT/directory).rglob('*')
            if p.is_file() and '__pycache__' not in p.parts and not p.is_relative_to(DEST)}


def main():
    if (DEST/'run_started.json').exists():
        raise ValueError('本次单组重放已启动过；拒绝无记录重复运行')
    before = hashes()
    write_json('sha256_before.json',before)
    write_json('run_started.json',dict(alpha=.90,**{'lambda':.25},start_date='2025-02-01',
        label='PATH REPLAY DIAGNOSTIC ONLY / NOT FORMAL',
        historical_frozen_list_test='已知Q4 21/22中的旧全目录清单失败单独保留，未更新或忽略旧清单；本次仍执行protect并核对运行前后全体文件SHA'))
    tick = perf_counter()
    state = dict(last_completed_date=None,last_progress_date=None,successful_plan_updates=0)

    def observed_plan(*args,date,directory,solver,**kwargs):
        bound = SIGNATURE.bind(*args,**kwargs)
        bound.apply_defaults()
        v = bound.arguments
        # 原日循环已经生成场景；只读其局部上下文，不重新预测、不改变传入数组。
        frame = inspect.currentframe().f_back
        while frame is not None and frame.f_code is not simulate_day.__code__:
            frame = frame.f_back
        if frame is None:
            raise RuntimeError('找不到原日循环场景上下文，停止而不猜测历史日期')
        scenario = frame.f_locals['scenario']
        n = len(v['price'])
        context = dict(date=str(date),update_time=f'{(144-n)//6:02d}:00',slot=145-n,
            horizon_start=145-n,horizon_length=n,current_soc=float(v['start_soc']),
            scenario_count=len(scenario['dates']),scenario_dates=list(map(str,scenario['dates'])),
            scenario_probabilities=list(map(float,scenario['probability'])),alpha=.90,**{'lambda':.25})
        del frame
        state['active_plan'] = context
        arrays = {k:np.asarray(v[k]).copy() for k in ('load_scenarios','pv_scenarios','price','start_soc','alpha','risk_weight')}
        arrays.update(previous_plan=np.asarray([] if v['previous_plan'] is None else v['previous_plan']),
            previous_plan_present=np.asarray(v['previous_plan'] is not None),
            scenario_dates=np.asarray(context['scenario_dates']),scenario_probabilities=scenario['probability'],date=np.asarray(str(date)))
        np.savez(DEST/'active_plan_context.npz',**arrays)
        write_json('active_plan_context.json',context)
        try:
            result = diagnostic_plan(*args,date=date,directory=DEST,solver=solver,**kwargs)
        except Exception:
            failures = sorted(DEST.glob('plan_failure_*.json'))
            captured = json.loads(failures[-1].read_text(encoding='utf-8')) if failures else {}
            write_json('failure_context.json',dict(context,solver_capture=captured,
                previous_success='last_successful_plan.json',
                exact_context_npz='active_plan_context.npz',
                phase_confirmed=captured.get('primary_status')=='optimal' and captured.get('failed_stage')=='secondary'))
            raise
        # 只保留最近一次成功更新，异常时不会被失败方案覆盖。
        np.savez(DEST/'last_successful_plan.npz',**arrays,grid=result['grid'],increase=result['increase'],decrease=result['decrease'],
                 scenario_terminal_soc=result['scenario_terminal_soc'])
        write_json('last_successful_plan.json',dict(context,primary_star=result['primary_star'],
            primary_status=result['primary_status'],secondary_status=result['secondary_status'],
            primary_objective=result['primary_objective'],secondary_throughput=result['secondary_throughput'],
            max_violation=result['max_violation']))
        state['successful_plan_updates'] += 1
        return result

    def negative_output(error,alpha,risk_weight,start_soc,directory):
        return save_negative_input(error,alpha,risk_weight,start_soc,DEST)

    adapted_day = FunctionType(run_day.__code__,dict(run_day.__globals__,diagnostic_plan=observed_plan,
                             save_negative_input=negative_output),argdefs=run_day.__defaults__)

    def day_observer(*args,**kwargs):
        state['last_started_date'] = str(args[0])
        result = adapted_day(*args,**kwargs)
        state['last_completed_date'] = str(args[0])
        write_json('path_progress.json',state)
        return result

    # 逐日推进仍用原年度函数：缓存、初始6000、SOC传递、价格及观测顺序全部不变。
    annual = FunctionType(run_dates.__code__,dict(run_dates.__globals__,run_three=day_observer),argdefs=run_dates.__defaults__)
    status = 'not_started'
    try:
        with protect(ROOT):
            history,prices,issues = load_inputs(ROOT)
            def progress(n,total,date):
                state['last_progress_date'] = str(date)
                print(f'PATH DIAGNOSTIC alpha=0.90 lambda=0.25 {n}/{total}: {date}',flush=True)
            annual(history,prices,issues,3,FORMAL_DATES,'PATH REPLAY DIAGNOSTIC ONLY / NOT FORMAL',.90,.25,progress)
            status = '真实故障未复现'
    except Exception as error:
        message = str(error)
        status = 'SCIP_LP_FAILURE_REPRODUCED' if ('error in LP solver' in message or 'unresolved numerical troubles' in message) else 'STOPPED_OTHER_ERROR'
        state['error'] = message
        (DEST/'exception.txt').write_text(traceback.format_exc(),encoding='utf-8')
    finally:
        after = hashes()
        differences = [p for p in sorted(set(before)|set(after)) if before.get(p)!=after.get(p)]
        write_json('sha256_after.json',after)
        write_json('replay_result.json',dict(status=status,alpha=.90,**{'lambda':.25},runtime_seconds=perf_counter()-tick,
            **state,sha256_unchanged=not differences,changed_protected_files=differences,
            mathematical_changes=False,formal_outputs_written=False,search_started=False,manifest_migrated=False))
        if differences:
            raise RuntimeError(f'重放期间保护文件变化：{differences}')
        print(json.dumps(dict(status=status,**state,runtime_seconds=perf_counter()-tick),ensure_ascii=False,indent=2),flush=True)


if __name__=='__main__':
    main()
