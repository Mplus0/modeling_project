"""方案A隔离实验：复用冻结函数AST，只替换freeTransform为全新模型构造。"""
import ast
import copy
import inspect
import json
import sys
from pathlib import Path
from time import perf_counter
import numpy as np

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0,str(ROOT))
from src.q3.optimizer import solve_plan, VALIDATION_TOL
from src.common.data_loader import file_hash
from src.q4.inputs import protect
from run_path_replay import hashes

DEST = Path(__file__).resolve().parent/'scheme_a'
SOURCE = Path(__file__).resolve().parent/'plan_failure_a0p90_l0p25_2025-05-30_s73_20260912T201130394419Z.npz'


def make_solver():
    tree = ast.parse(inspect.getsource(solve_plan))
    function = tree.body[0]
    index = next(i for i,node in enumerate(function.body) if isinstance(node,ast.Try))
    construction = copy.deepcopy(function.body[:index])
    attempt = function.body[index]
    transition = [i for i,node in enumerate(attempt.body) if isinstance(node,ast.Expr)
                  and isinstance(node.value,ast.Call) and isinstance(node.value.func,ast.Attribute)
                  and node.value.func.attr=='freeTransform']
    if len(transition)!=1:
        raise ValueError('冻结求解器结构变化，拒绝猜测二级构造位置')
    # 保存一级grid供比较，然后释放一级模型；重新执行同一变量/约束构造AST。
    replacement = ast.parse('primary_grid_snapshot = np.array([model.getVal(v) for v in grid])\nmodel.freeProb()').body
    attempt.body[transition[0]:transition[0]+1] = replacement+construction
    returned = function.body[-1]
    if not isinstance(returned,ast.Return) or not isinstance(returned.value,ast.Call):
        raise ValueError('冻结返回结构变化')
    returned.value.keywords.append(ast.keyword(arg='primary_grid_snapshot',value=ast.Name(id='primary_grid_snapshot',ctx=ast.Load())))
    # 双侧锁、throughput目标、求解设置、取值和独立物理验收均使用原AST，不重写公式。
    ast.fix_missing_locations(tree)
    namespace = dict(solve_plan.__globals__)
    exec(compile(tree,'<Q4 scheme A: fresh secondary model>','exec'),namespace)
    return namespace['solve_plan']


def main():
    DEST.mkdir(exist_ok=True)
    if (DEST/'started.json').exists():
        raise ValueError('方案A已启动，拒绝重复三次实验')
    original = json.loads(SOURCE.with_suffix('.json').read_text(encoding='utf-8'))
    if file_hash(SOURCE)!=original['npz_sha256']:
        raise ValueError('真实失败输入SHA不符')
    with np.load(SOURCE,allow_pickle=False) as data:
        args = [data[k].copy() for k in ('load_scenarios','pv_scenarios','price')]
        args += [float(data[k]) for k in ('start_soc','alpha','risk_weight')]
        args += [data['previous_plan'].copy() if bool(data['previous_plan_present']) else None]
    def save(name,value):
        (DEST/name).write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    before = hashes()
    save('started.json',dict(input_sha256=file_hash(SOURCE),source_sha256=file_hash(ROOT/'src/q3/optimizer.py'),
        alpha=args[4],**{'lambda':args[5]},baseline='原实现同一输入3/3二级失败',COST_LOCK_TOLERANCE=1e-7,SOLVER_FEASTOL=1e-9))
    solver = make_solver()
    rows = []
    try:
        with protect(ROOT):
            for i in range(1,4):
                tick = perf_counter()
                try:
                    result = solver(*args)
                    row = dict(attempt=i,success=True,primary_star=result['primary_star'],secondary_status=result['secondary_status'],
                        secondary_objective=result['secondary_throughput'],primary_value=result['primary_objective'],
                        primary_lock_error=abs(result['primary_objective']-result['primary_star']),max_constraint_violation=result['max_violation'],
                        grid_max_difference_from_primary=float(np.max(np.abs(result['grid']-result['primary_grid_snapshot']))),
                        cvar=result['cvar_auxiliary'],empirical_cvar=result['cvar_empirical'],throughput=result['secondary_throughput'])
                    np.savez(DEST/f'attempt_{i}.npz',grid=result['grid'],primary_grid=result['primary_grid_snapshot'],
                             increase=result['increase'],decrease=result['decrease'],xi=result['xi'],zeta=result['zeta'])
                    if abs(result['primary_star']-original['primary_star'])>VALIDATION_TOL:
                        raise ValueError('一级star与原路径不符')
                except Exception as error:
                    # 只读取本次真实异常栈，保存第二阶段失败时可用的一级star。
                    trace = error.__traceback__
                    values = {}
                    while trace:
                        if trace.tb_frame.f_code is solver.__code__:
                            values = trace.tb_frame.f_locals
                        trace = trace.tb_next
                    row = dict(attempt=i,success=False,error=str(error),primary_star=values.get('star'),
                        primary_status=values.get('first_status'),secondary_status=values.get('second_status','LP_ERROR'),
                        secondary_objective=None,primary_value=None,primary_lock_error=None,max_constraint_violation=None,
                        grid_max_difference_from_primary=None,cvar=None,throughput=None)
                row['runtime_seconds'] = perf_counter()-tick
                rows.append(row)
                save('results.json',dict(attempts=rows,all_three_success=len(rows)==3 and all(r['success'] for r in rows)))
                print(json.dumps(row,ensure_ascii=False),flush=True)
    finally:
        after = hashes()
        changes = [p for p in set(before)|set(after) if before.get(p)!=after.get(p)]
        save('integrity.json',dict(sha256_unchanged=not changes,changes=changes,protected_files=len(before)))
        if changes:
            raise RuntimeError(f'保护文件变化：{changes}')


if __name__=='__main__':
    main()
