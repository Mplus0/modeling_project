"""只读核验搜索完整组/签名，或重放一个已有真实计划失败快照；不启动搜索。"""
import argparse
import json
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from src.common.data_loader import file_hash
from src.q4.inputs import frozen_hashes
from src.q4.metrics import load_outputs
from src.q4.validation import validate_outputs
from src.q4.plan_diagnostics import replay_snapshot
from src.q3.parameters import PARAMETER_GRID


def audit(root):
    search = root/'outputs/q4/search'
    target = root/'outputs/q4/diagnostics'
    target.mkdir(parents=True,exist_ok=True)
    manifest_path = search/'manifest.json'
    manifest_hash = file_hash(manifest_path)
    previous = json.loads(manifest_path.read_text(encoding='utf-8'))
    current = frozen_hashes(root)
    current.update({str(p.relative_to(root)):file_hash(p) for p in (root/'src/q4').glob('*.py')})
    changes = [dict(path=name,change='added' if name not in previous else 'removed' if name not in current else 'modified',
                    before=previous.get(name),after=current.get(name))
               for name in sorted(set(previous)|set(current)) if previous.get(name)!=current.get(name)]
    progress = json.loads((search/'progress.json').read_text(encoding='utf-8'))
    groups = []
    # 逐组只读复算；回执必须覆盖所有输出表、指标及验证文件，不能仅检查回执里碰巧存在的几项。
    for alpha,weight in PARAMETER_GRID:
        folder = search/f'groups/a{alpha:.2f}_l{weight:.2f}'
        if not folder.exists():
            continue
        item = dict(alpha=alpha,**{'lambda':weight},directory=str(folder.relative_to(root)),reusable=False)
        try:
            receipt_path = folder/'completed_sha256.json'
            receipt_digest = file_hash(receipt_path)
            hashes = json.loads(receipt_path.read_text(encoding='utf-8'))
            if not hashes:
                raise ValueError('空回执')
            for name,digest in hashes.items():
                candidate = (folder/name).resolve()
                if not candidate.is_relative_to(folder.resolve()) or not candidate.is_file() or file_hash(candidate)!=digest:
                    raise ValueError(f'回执文件缺失或SHA错误：{name}')
            outputs,metrics = load_outputs(folder)
            required = {'q4_metrics.json','q4_validation.json'}|{f'q4_{key}.csv' for key in metrics['output_tables']}
            if not required.issubset(hashes):
                raise ValueError('回执未覆盖所有正式输出')
            if (metrics.get('alpha'),metrics.get('lambda'),metrics.get('variant'),metrics.get('formal'),metrics.get('run_label'))!=(alpha,weight,3,True,'Q4-3 SEARCH'):
                raise ValueError('参数/正式标签不符')
            for key,frame in outputs.items():
                for column,value in (('alpha',alpha),('lambda',weight),('run_label','Q4-3 SEARCH')):
                    if column in frame and not frame[column].eq(value).all():
                        raise ValueError(f'{key}参数/标签不一致')
            checked = validate_outputs(outputs,3,formal=True)
            if file_hash(receipt_path)!=receipt_digest or any(file_hash(folder/p)!=h for p,h in hashes.items()):
                raise ValueError('验证期间组文件变化')
            item.update(reusable=True,checked_files=len(hashes),receipt_sha256=receipt_digest,validation=checked)
        except Exception as error:
            item['error'] = str(error)
        groups.append(item)
        print(f'Validated {folder.name}: {item["reusable"]}',flush=True)
    if file_hash(manifest_path)!=manifest_hash:
        raise RuntimeError('审计期间manifest发生变化')
    report = dict(manifest_sha256=manifest_hash,signature_changes=changes,groups=groups,progress=progress,
                  migration_applied=False,search_started=False,
                  failure_context=dict(alpha=.90,**{'lambda':.25},date_min='2025-05-22',date_max='2025-05-31',
                     exact_date=None,update_time=None,primary_star=None,source='用户提供的第12组及110天进度日志',
                     exact_replay_available=False))
    (target/'plan_failure_search_audit.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    lines = ['# Q4计划LP故障：搜索文件只读审计','',
             '失败组由用户日志确认为0.90/0.25；日期只能限定在2025-05-22至2025-05-31。没有本次真实LP输入，未进行伪造初态重放。','',
             '## 与搜索启动manifest的逐项差异','',* [f'- {r["change"]}: `{r["path"]}`' for r in changes], '',
             '## 已有组验收','',* [f'- {r["directory"]}: {"通过" if r["reusable"] else r.get("error")}' for r in groups], '',
             '## 待审核的签名迁移方案','',
             '不执行迁移。待真实故障诊断完成、用户批准后：先按时间戳备份原manifest与progress，记录备份SHA；逐项审核上述diff并重验完整组回执；仅把已批准的非计算输出新增及已测试的Q4诊断代码变更纳入新签名。记录旧/新签名、理由、批准记录和验证结果，再原子替换manifest。任何额外输入/模型/正式结果差异必须停止。保留原组回执及其原始来源签名，不改写已完成组。','',
             '目前不能直接使用--resume；未启动全年、参数搜索或提交。']
    (target/'plan_failure_search_audit.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(json.dumps(dict(valid_groups=sum(g['reusable'] for g in groups),signature_changes=changes),ensure_ascii=False,indent=2),flush=True)
    return report


if __name__=='__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snapshot',type=Path,help='仅重放指定失败NPZ；不提供则只读审计已有组')
    parser.add_argument('--repeats',type=int,choices=(1,2,3),default=1)
    args = parser.parse_args()
    if args.snapshot:
        print(json.dumps(replay_snapshot(args.snapshot,args.repeats),ensure_ascii=False,indent=2))
    else:
        audit(ROOT)
