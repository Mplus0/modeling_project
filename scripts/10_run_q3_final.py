"""固定团队已确认winner；用户执行全年重跑，通过验收后自动写最终交接文件。"""

import argparse
import json
from pathlib import Path
from time import perf_counter
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

from src.common.data_loader import file_hash
from src.q2.forecasting import load_daily_inputs
from src.q3.annual import FORMAL_DATES, run_dates
from src.q3.forecast import load_hourly_forecasts
from src.q3.metrics import write_annual_outputs
from src.q3.final import FINAL_ALPHA, FINAL_LAMBDA, FINAL_LABEL, read_confirmed_selection, load_final, validate_final, compare_search_winner
from src.q3.result_writer import inspect_template, write_result3
from src.q3.final_reports import write_paper_reports
from src.q3.search_runner import save_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check-only",action="store_true",help="仅读取并验证固定winner及官方模板，不运行全年")
    args = parser.parse_args()
    directory = ROOT/"outputs/q3/final"
    if directory.resolve()!=ROOT.resolve()/"outputs/q3/final":
        parser.error("最终输出目录不能链接至冻结输出")
    protected = [p for folder in (ROOT/"data",ROOT/"src/common",ROOT/"src/q1",ROOT/"src/q2",ROOT/"outputs")
                 for p in folder.rglob("*") if p.is_file() and "__pycache__" not in p.parts
                 and not p.is_relative_to(directory) and p!=ROOT/"outputs/submissions/result3.xlsx"]
    before = {str(p.relative_to(ROOT)):file_hash(p) for p in protected}
    def integrity():
        if any(file_hash(ROOT/p)!=h for p,h in before.items()):
            raise RuntimeError("Q3最终运行检测到冻结文件SHA-256变化")
        return dict(sha256_unchanged=True,files_checked=len(before),sha256=before)
    try:
        ranking,selection,winner_daily,winner_metrics = read_confirmed_selection(ROOT)
        template = inspect_template(ROOT/"data/raw/附件5/result3.xlsx")
        print(f"Q3 FINAL alpha={FINAL_ALPHA} lambda={FINAL_LAMBDA}",flush=True)
        if args.check_only:
            print(json.dumps(dict(winner_confirmed=True,best_score=selection["best_score"],template=template),ensure_ascii=False,indent=2))
            return
        started = perf_counter()
        history,price = load_daily_inputs(ROOT/"data/processed/historical_power.csv",ROOT/"data/processed/q1_input.csv")
        issues = load_hourly_forecasts(ROOT/"data/processed/pv_forecast_hourly.csv")
        progress = lambda count,total,day: print(f"Q3 FINAL completed {count}/{total} days: {day}",flush=True)
        # 与搜索完全相同的年度引擎和初始SOC，不允许CLI覆盖最终参数。
        outputs,timings = run_dates(history,issues,price,FORMAL_DATES,6000.,FINAL_ALPHA,FINAL_LAMBDA,progress)
        timings["runtime_seconds"] = perf_counter()-started
        metrics = write_annual_outputs(outputs,directory,timings,integrity())
        # 计算完成后仅修改结果身份标签，底层数值保持求解器返回的原始浮点值。
        metrics["run_label"] = FINAL_LABEL
        save_json(directory/"q3_annual_metrics.json",metrics)
        for name,frame in outputs.items():
            if "run_label" in frame:
                frame["run_label"] = FINAL_LABEL
                frame.to_csv(directory/f"q3_{name}.csv",index=False,encoding="utf-8-sig")
        # 重新读盘独立复核，Excel只能使用这些最终CSV。
        outputs,metrics = load_final(directory)
        try:
            validation = validate_final(outputs,metrics)
        except (ValueError, AssertionError) as error:
            # 验收失败也保留诊断；不得继续写入正式提交文件。
            save_json(directory/"q3_final_validation.json",dict(passed=False,error=str(error),
                      integrity=integrity(),submission_status="not_generated"))
            raise
        comparison = compare_search_winner(outputs["daily_metrics"],metrics,winner_daily,winner_metrics)
        save_json(directory/"q3_search_vs_final_comparison.json",comparison)
        validation.update(search_winner_comparison_passed=comparison["passed"],integrity=integrity(),submission_status="not_generated")
        save_json(directory/"q3_final_validation.json",validation)
        if not comparison["passed"]:
            raise RuntimeError("Q3最终与搜索winner不一致，已保存诊断，未生成result3.xlsx")
        q2 = json.loads((ROOT/"outputs/q2/q2_metrics.json").read_text(encoding="utf-8"))
        write_paper_reports(directory,outputs,metrics,ranking,selection,q2,"等待模板副本写入",[])
        submission = write_result3(ROOT)
        validation.update(submission_status="generated",submission_validation=submission,integrity=integrity())
        save_json(directory/"q3_final_validation.json",validation)
        write_paper_reports(directory,outputs,metrics,ranking,selection,q2,"已生成outputs/submissions/result3.xlsx并验证",[])
        # README仅更新预留状态块，不改动其他问题说明。
        readme = ROOT/"README.md"
        text = readme.read_text(encoding="utf-8")
        left,right = "<!-- Q3_FINAL_STATUS_BEGIN -->","<!-- Q3_FINAL_STATUS_END -->"
        if text.count(left)==text.count(right)==1:
            prefix,tail = text.split(left,1)
            _,suffix = tail.split(right,1)
            readme.write_text(prefix+left+"\n最终全年完整重跑、搜索一致性对比、独立验收及result3.xlsx生成均已完成；论文交接文件已输出，等待人工最终审阅。\n"+right+suffix,encoding="utf-8")
        print(json.dumps(dict(status="complete",alpha=FINAL_ALPHA,**{"lambda":FINAL_LAMBDA},
                              total_actual_cost_yuan=metrics["total_actual_cost_yuan"],submission="outputs/submissions/result3.xlsx"),ensure_ascii=False,indent=2))
    finally:
        integrity()


if __name__=="__main__":
    main()
