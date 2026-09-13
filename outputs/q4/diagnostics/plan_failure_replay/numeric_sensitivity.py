"""真实单LP的有限参数诊断；每次仅改变二级LP的一个数值设置。"""
import json
import sys
import traceback
from pathlib import Path
from time import perf_counter
from types import FunctionType
import numpy as np
import pyscipopt
from pyscipopt import Model

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0,str(ROOT))
from src.q3.optimizer import solve_plan, VALIDATION_TOL, COST_LOCK_TOLERANCE, SOLVER_FEASTOL
from src.common.data_loader import file_hash
from src.q4.inputs import protect
from run_path_replay import hashes

DEST = Path(__file__).resolve().parent/'numeric_sensitivity'
SOURCE = Path(__file__).resolve().parent/'plan_failure_a0p90_l0p25_2025-05-30_s73_20260912T201130394419Z.npz'


def configured_solver(settings):
    if any(k in ('numerics/feastol','numerics/epsilon','numerics/dualfeastol','numerics/lpfeastolfactor') for k in settings):
        raise ValueError('本实验不调整任何可行性或最优性容差')
    class NumericModel(Model):
        def optimize(self):
            self.diagnostic_calls = getattr(self,'diagnostic_calls',0)+1
            if self.diagnostic_calls==2:
                for name,value in settings.items():
                    self.setParam(name,value)
                if self.getParam('numerics/feastol')!=SOLVER_FEASTOL:
                    raise ValueError('禁止修改既有feastol')
            return super().optimize()
    return FunctionType(solve_plan.__code__,dict(solve_plan.__globals__,Model=NumericModel),argdefs=solve_plan.__defaults__)


def main():
    DEST.mkdir(exist_ok=True)
    if (DEST/'started.json').exists():
        raise ValueError('有限参数诊断已启动，拒绝无记录重复运行')
    def save(name,value):
        (DEST/name).write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    before = hashes()
    old = json.loads(SOURCE.with_suffix('.json').read_text(encoding='utf-8'))
    if file_hash(SOURCE)!=old['npz_sha256']:
        raise ValueError('真实快照SHA不符')
    with np.load(SOURCE,allow_pickle=False) as data:
        args = [data[k].copy() for k in ('load_scenarios','pv_scenarios','price')]
        args += [float(data[k]) for k in ('start_soc','alpha','risk_weight')]
        args += [data['previous_plan'].copy() if bool(data['previous_plan_present']) else None]
    model = Model()
    defaults = model.getParams()
    discovered = {k:v for k,v in defaults.items() if k.startswith(('lp/','numerics/')) or any(s in k.lower() for s in ('scal','refin','condition','stabil'))}
    versions = dict(pyscipopt=pyscipopt.__version__,scip=f'{model.getMajorVersion()}.{model.getMinorVersion()}.{model.getTechVersion()}',
                    lp_solver='SoPlex 8.0.2 (由当前printVersion输出确认)')
    model.freeProb()
    save('available_parameters.json',dict(versions=versions,defaults=discovered,
         note='numerics/feastol的SCIP默认值不同于项目值；全部实验仍由冻结代码设置为1e-9'))
    candidates = [('default',{}),('scaling_off',{'lp/scaling':0}),('scaling_aggressive',{'lp/scaling':2}),
                  ('markowitz_stability',{'lp/minmarkowitz':.1}),('frequent_refactor',{'lp/refactorinterval':10}),
                  ('lp_presolve_off',{'lp/presolving':False})]
    if any(k not in defaults for _,s in candidates for k in s):
        raise ValueError('候选参数不在当前安装环境中')
    save('started.json',dict(versions=versions,input_sha256=file_hash(SOURCE),COST_LOCK_TOLERANCE=COST_LOCK_TOLERANCE,
        SOLVER_FEASTOL=SOLVER_FEASTOL,VALIDATION_TOL=VALIDATION_TOL,candidates=[dict(name=n,settings=s) for n,s in candidates],
        application_stage='仅第二次optimize之前'))
    rows = []
    def attempt(name,settings,index,phase):
        solver = configured_solver(settings)
        tick = perf_counter()
        row = dict(configuration=name,phase=phase,attempt=index,
                   parameters={k:dict(original=defaults[k],new=v) for k,v in settings.items()})
        try:
            result = solver(*args)
            finite = all(np.isfinite(f.select_dtypes(include=[np.number]).to_numpy()).all() for f in result['scenario_schedules'])
            error = abs(result['primary_objective']-result['primary_star'])
            row.update(success=bool(finite and result['secondary_status']=='optimal' and error<=VALIDATION_TOL and
                       result['max_violation']<=VALIDATION_TOL and abs(result['primary_star']-old['primary_star'])<=VALIDATION_TOL),
                primary_status=result['primary_status'],primary_star=result['primary_star'],secondary_status=result['secondary_status'],
                secondary_objective=result['secondary_throughput'],primary_value=result['primary_objective'],primary_lock_error=error,
                max_constraint_violation=result['max_violation'],throughput=result['secondary_throughput'],cvar=result['cvar_auxiliary'],
                empirical_cvar=result['cvar_empirical'],grid_min=float(result['grid'].min()),grid_max=float(result['grid'].max()),finite=bool(finite))
            np.savez(DEST/f'{name}_{phase}_{index}.npz',grid=result['grid'],increase=result['increase'],decrease=result['decrease'],
                     zeta=result['zeta'],xi=result['xi'])
        except Exception as exc:
            trace = exc.__traceback__
            values = {}
            while trace:
                if trace.tb_frame.f_code is solve_plan.__code__:
                    values = trace.tb_frame.f_locals
                trace = trace.tb_next
            row.update(success=False,error=str(exc),primary_status=values.get('first_status'),primary_star=values.get('star'),
                secondary_status=values.get('second_status','LP_ERROR'),secondary_objective=None,primary_value=None,
                primary_lock_error=None,max_constraint_violation=None,throughput=None,cvar=None,grid_min=None,grid_max=None)
            (DEST/f'{name}_{phase}_{index}_error.txt').write_text(traceback.format_exc(),encoding='utf-8')
        row['runtime_seconds'] = perf_counter()-tick
        rows.append(row)
        save('results.json',rows)
        print(json.dumps(row,ensure_ascii=False),flush=True)
        return row
    selected = None
    try:
        with protect(ROOT):
            for name,settings in candidates:
                initial = [attempt(name,settings,i,'three') for i in range(1,4)]
                if settings and all(r['success'] for r in initial):
                    repeat = [attempt(name,settings,i,'ten') for i in range(1,11)]
                    if all(r['success'] for r in repeat):
                        selected = dict(name=name,settings=settings,ten_success=True,
                            throughput_range=float(np.ptp([r['throughput'] for r in repeat])),
                            max_primary_lock_error=max(r['primary_lock_error'] for r in repeat),
                            max_constraint_violation=max(r['max_constraint_violation'] for r in repeat))
                        break
            save('selection.json',dict(selected=selected,attempt_count=len(rows)))
    finally:
        after = hashes()
        changes = [p for p in set(before)|set(after) if before.get(p)!=after.get(p)]
        save('integrity.json',dict(sha256_unchanged=not changes,changes=changes,protected_files=len(before)))
        if changes:
            raise RuntimeError(f'保护文件变化：{changes}')


if __name__=='__main__':
    main()
