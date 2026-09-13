"""Q4命令入口共用加载与保护；smoke和全年路径明确分离。"""

import argparse
from datetime import date,timedelta
from src.q3.annual import FORMAL_DATES
from src.q4.inputs import load_inputs, protect
from src.q4.annual import run_dates
from src.q4.metrics import write_outputs
from src.q4.q4_3 import REFERENCE_LABEL


def main(mode, root):
    parser = argparse.ArgumentParser(description=f"Q4 {mode}")
    if mode=="smoke":
        parser.add_argument("--days",type=int,choices=(1,2,3),default=1)
        parser.add_argument("--start",type=date.fromisoformat,default=date(2025,3,20))
    if mode=="search":
        parser.add_argument("--resume",action="store_true")
    if mode=="write":
        parser.add_argument("--variant",type=int,choices=(2,3),required=True)
        parser.add_argument("--human-approved",action="store_true",help="仅在完整全年结果已经人工验收后使用")
    args = parser.parse_args()
    # 导出器自己核对逐文件SHA；独立审计新增文件不能触发旧全outputs集合保护。
    if mode=="write":
        if not args.human_approved:
            parser.error("正式Q4提交必须先人工验收全年结果，再显式指定--human-approved")
        from src.q4.result_writer import write_submission
        write_submission(root,args.variant,human_approved=True)
        return
    with protect(root) as integrity:
        history,prices,issues = load_inputs(root)
        if mode=="search":
            from src.q4.search import run_search
            run_search(root,history,prices,issues,integrity,args.resume)
            return
        variants = (2,3) if mode=="smoke" else (2,) if mode=="q4_2" else (3,)
        dates = tuple(args.start+timedelta(days=i) for i in range(args.days)) if mode=="smoke" else FORMAL_DATES
        for variant in variants:
            if mode=="smoke":
                label = "Q4 SMOKE / TEST ONLY"
                directory = root/f"outputs/q4/smoke/q4_{variant}"
            elif variant==2:
                label,directory = "Q4-2 ANNUAL / AWAITING HUMAN REVIEW",root/"outputs/q4/q4_2"
            else:
                label,directory = REFERENCE_LABEL,root/"outputs/q4/reference/q4_3_a0.85_l0.25"
            outputs,runtime = run_dates(history,prices,issues,variant,dates,label,
                                        progress=lambda n,total,d:print(f"{label} completed {n}/{total}: {d}",flush=True))
            metrics = write_outputs(directory,outputs,variant,runtime,label,integrity,formal=mode!="smoke")
            print(f"Q4-{variant}: days={metrics['days']}, slots={metrics['slots']}, max_violation={metrics['max_constraint_violation']}, runtime_seconds={runtime:.2f}",flush=True)
