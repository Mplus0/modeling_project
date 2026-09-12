"""未来20组动态价格全年搜索；逐组独立SOC，直接复用Q3统一评分。"""

import json
import pandas as pd
from src.common.data_loader import file_hash
from src.q3.parameters import PARAMETER_GRID
from src.q3.search import score_annual_results
from src.q3.search_runner import save_json
from src.q3.annual import FORMAL_DATES
from src.q4.annual import run_dates
from src.q4.metrics import write_outputs, load_outputs
from src.q4.validation import validate_outputs


def run_search(root, history, prices, issues, integrity, resume=False):
    directory = root/"outputs/q4/search"
    directory.mkdir(parents=True,exist_ok=True)
    signature = dict(integrity)
    signature.update({str(p.relative_to(root)):file_hash(p) for p in (root/"src/q4").glob("*.py")})
    manifest = directory/"manifest.json"
    if manifest.exists():
        if not resume or json.loads(manifest.read_text(encoding="utf-8"))!=signature:
            raise ValueError("Q4搜索已有记录：需--resume且输入/代码SHA一致")
    else:
        save_json(manifest,signature)
    daily_results,groups = [],[]
    for index,(alpha,weight) in enumerate(PARAMETER_GRID,1):
        folder = directory/f"groups/a{alpha:.2f}_l{weight:.2f}"
        print(f"Q4-3 search [{index:02d}/20] alpha={alpha} lambda={weight}",flush=True)
        receipt = folder/"completed_sha256.json"
        if resume and receipt.exists():
            hashes = json.loads(receipt.read_text(encoding="utf-8"))
            if not hashes or any(not (folder/p).is_file() or file_hash(folder/p)!=h for p,h in hashes.items()):
                raise ValueError("Q4恢复组文件损坏，停止搜索")
            outputs,metrics = load_outputs(folder)
            if (metrics.get("alpha"),metrics.get("lambda"))!=(alpha,weight):
                raise ValueError("Q4恢复组参数不匹配")
            validate_outputs(outputs,3,formal=True)
        else:
            outputs,runtime = run_dates(history,prices,issues,3,FORMAL_DATES,"Q4-3 SEARCH",alpha,weight,
                                        lambda n,total,d:print(f"Q4-3 group completed {n}/{total}: {d}",flush=True))
            write_outputs(folder,outputs,3,runtime,"Q4-3 SEARCH",integrity,formal=True)
            save_json(receipt,{p.name:file_hash(p) for p in folder.iterdir() if p.is_file() and p!=receipt})
        daily_results.append(outputs["daily_metrics"])
        groups.append(dict(alpha=alpha,**{"lambda":weight},directory=str(folder.relative_to(root))))
        save_json(directory/"progress.json",dict(completed_groups=len(groups),groups=groups))
    # 只有全部20组完成后才调用原评分，不对部分结果归一化。
    ranking,winners = score_annual_results(pd.concat(daily_results,ignore_index=True))
    ranking.to_csv(directory/"q4_parameter_ranking.csv",index=False,encoding="utf-8-sig")
    save_json(directory/"q4_search_summary.json",dict(completed_groups=20,winners=winners.to_dict("records"),
              winner_count=len(winners),best_score=float(ranking.Score.min()),human_review_required=True))
    if len(winners)==1:
        alpha,weight = winners.iloc[0][["alpha","lambda"]]
        outputs,metrics = load_outputs(directory/f"groups/a{alpha:.2f}_l{weight:.2f}")
        # 最终候选明细来自同一动态价格实验；人工验收前绝不写正式提交。
        for frame in outputs.values():
            if "run_label" in frame:
                frame["run_label"] = "Q4-3 FINAL CANDIDATE / AWAITING HUMAN REVIEW"
        write_outputs(root/"outputs/q4/final",outputs,3,metrics["runtime_seconds"],
                      "Q4-3 FINAL CANDIDATE / AWAITING HUMAN REVIEW",integrity,formal=True)
    return ranking,winners
