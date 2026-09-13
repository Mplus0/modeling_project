"""对已捕获真实输入原样重放三次，只写本诊断目录并保留完整性保护。"""
import json
from pathlib import Path
from time import perf_counter
from run_path_replay import ROOT, DEST, hashes, write_json
from src.q4.inputs import protect
from src.q4.plan_diagnostics import replay_snapshot

SNAPSHOT = 'plan_failure_a0p90_l0p25_2025-05-30_s73_20260912T201130394419Z.npz'


if __name__=='__main__':
    if Path.cwd().resolve()!=DEST.resolve():
        raise ValueError('必须从本诊断目录运行，以相对ASCII路径导出SCIP文件')
    if (DEST/'three_lp_replays_started.json').exists():
        raise ValueError('三次独立重放已经启动过，拒绝重复求解')
    before = hashes()
    original = json.loads((DEST/'sha256_before.json').read_text(encoding='utf-8'))
    # 数学代码和输入必须与真实路径重放时相同；其他结果仍由前后SHA保护。
    changed = [p for p in set(before)|set(original) if p.startswith(('src\\','data\\')) and before.get(p)!=original.get(p)]
    if changed:
        raise ValueError(f'原路径使用的代码/输入变化，停止：{changed}')
    write_json('three_lp_replays_sha256_before.json',before)
    write_json('three_lp_replays_started.json',dict(snapshot=SNAPSHOT,attempt_limit=3,mathematical_settings_changed=False))
    tick = perf_counter()
    try:
        with protect(ROOT):
            # 尝试相对文件名导出；SCIP仍可能展开绝对路径而导出失败，该错误独立记录。
            results = replay_snapshot(Path(SNAPSHOT),3)
            captures = []
            for result in results:
                matching = [n.split('Q4计划失败快照：',1)[1] for n in result.get('notes',[]) if n.startswith('Q4计划失败快照：')]
                captures.append(json.loads(Path(matching[0]).read_text(encoding='utf-8')) if matching else None)
            stable = all(c is not None and c['primary_status']=='optimal' and c['failed_stage']=='secondary'
                         and c['optimize_calls']==2 and 'error in LP solver' in c['error'] for c in captures)
            write_json('three_lp_replays_result.json',dict(attempts=results,captures=captures,
                stable_secondary_lp_failure=stable,runtime_seconds=perf_counter()-tick))
            print(json.dumps(dict(stable_secondary_lp_failure=stable,
                attempts=[dict(attempt=r['attempt'],success=r['success'],
                    primary_star=c['primary_star'] if c else r.get('primary_star'),
                    failed_stage=c['failed_stage'] if c else None) for r,c in zip(results,captures)]),ensure_ascii=False,indent=2))
    finally:
        after = hashes()
        changed = [p for p in set(before)|set(after) if before.get(p)!=after.get(p)]
        write_json('three_lp_replays_integrity.json',dict(sha256_unchanged=not changed,changes=changed,
                   code_and_inputs_match_original_path=True,protected_file_count=len(before)))
        if changed:
            raise RuntimeError(f'保护文件发生变化：{changed}')
