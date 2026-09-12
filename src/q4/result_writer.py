"""仅在人工验收后填充官方Q4副本；复用Q2/Q3样式和已确认字段映射。"""

import json
from pathlib import Path
from shutil import copy2
from tempfile import TemporaryDirectory
import numpy as np
import pandas as pd
from openpyxl import load_workbook
from src.common.data_loader import file_hash
from src.q2.result_writer import write_outputs as write_two, emergency_intervals, slot_intervals
from src.q3.result_writer import _populate, verify_workbook
from src.q4.metrics import load_outputs
from src.q4.validation import validate_outputs


def render_copy(template, destination, outputs, variant):
    """底层模板复制器供临时合成测试；正式调用必须经过write_submission门槛。"""
    template,destination = Path(template),Path(destination)
    if template.resolve()==destination.resolve() or destination.is_symlink():
        raise ValueError("Q4输出不得覆盖模板")
    before = file_hash(template)
    actual,daily = outputs["actual_schedule"],outputs["daily_metrics"]
    destination.parent.mkdir(parents=True,exist_ok=True)
    with TemporaryDirectory(dir=destination.parent,prefix=".q4-template-") as tmp:
        staged = Path(tmp)/destination.name
        if variant==3:
            copy2(template,staged)
            book = load_workbook(staged)
            try:
                _populate(book,outputs)
                book.save(staged)
            finally:
                book.close()
            verify_workbook(template,staged,outputs)
        elif variant==2:
            # 仅写入视图采用真实结算费用，不修改计划CSV中的预测价格或目标。
            plan = outputs["plan_schedule"].copy()
            plan["planned_cost_slot_yuan"] = plan.settled_plan_cost_yuan
            view = daily.rename(columns={"soc_end_kwh":"soc_actual_end_kwh","plan_cost_00_yuan":"planned_cost_yuan",
                                         "actual_emergency_cost_yuan":"emergency_cost_yuan","total_actual_cost_yuan":"total_cost_yuan"}).copy()
            for stage in ("primary","secondary"):
                view[f"plan_{stage}_status"] = "optimal"
            for name in ("max_plan_constraint_violation","max_actual_constraint_violation","max_rolling_constraint_violation"):
                view[name] = daily.max_constraint_violation.to_numpy()
            view["planned_grid_purchase_kwh"] = plan.groupby("date",sort=False).grid_purchase_plan_kwh.sum().to_numpy()
            write_two(template,staged,plan,actual,view,Path(tmp)/"unused_paper.md")
        else:
            raise ValueError("Q4模板类型必须为2或3")
        verify_values(staged,outputs,variant)
        if file_hash(template)!=before:
            raise RuntimeError("Q4原模板哈希变化")
        staged.replace(destination)
    return dict(template_sha256=before,output_sha256=file_hash(destination),passed=True)


def verify_values(path, outputs, variant):
    """由CSV重算每日费用、24slot充放电和紧急区间，不依赖写入函数的返回值。"""
    book = load_workbook(path,data_only=True)
    try:
        names = ["计划购电量","充放电量","紧急购电量"] if variant==2 else ["计划购电量","调整购电量","充放电量","紧急购电量"]
        if book.sheetnames!=names or book["充放电量"].max_row!=2005:
            raise ValueError("Q4模板sheet或全年充放电结构不符")
        actual,daily = outputs["actual_schedule"],outputs["daily_metrics"]
        for i,row in enumerate(daily.itertuples()):
            a = actual[actual.date.eq(row.date)]
            grid = (outputs["plan_schedule"].loc[lambda f:f.date.eq(row.date),"grid_purchase_plan_kwh"].to_numpy()
                    if variant==2 else outputs["plan_updates"].loc[lambda f:f.date.eq(row.date)&f.update_time.eq("00:00"),"new_plan_kwh"].to_numpy())
            values = [book["计划购电量"].cell(i+2,col).value for col in range(2,148)]
            np.testing.assert_allclose(values,np.r_[grid,grid.sum(),row.plan_cost_00_yuan],atol=1e-6,rtol=0)
            for block in range(6):
                part = a.iloc[block*24:(block+1)*24]
                np.testing.assert_allclose([book["充放电量"].cell(2+i*6+block,c).value for c in (3,4)],
                                            [(part.x_real_kwh+part.q_real_kwh).sum(),part.z_real_kwh.sum()],atol=1e-6,rtol=0)
            np.testing.assert_allclose([book["充放电量"].cell(2+i*6,6).value,book["充放电量"].cell(3+i*6,6).value],
                                        [row.soc_start_kwh,row.soc_end_kwh],atol=1e-6,rtol=0)
            if variant==3:
                changes = outputs["plan_updates"].loc[lambda f:f.date.eq(row.date)&~f.update_time.eq("00:00")]
                net = (changes.increase_kwh-changes.decrease_kwh).groupby(changes.slot).sum().reindex(range(1,145),fill_value=0.)
                np.testing.assert_allclose([book["调整购电量"].cell(i+2,c).value for c in range(2,148)],
                                            np.r_[net,net.sum(),changes.adjustment_cost_yuan.sum()],atol=1e-6,rtol=0)
        labels = [book["计划购电量"].cell(1,c).value for c in range(2,146)]
        events = emergency_intervals(actual,slot_intervals(labels))
        if book["紧急购电量"].max_row!=len(events)+1:
            raise ValueError("Q4紧急购电区间数不符")
        for i,event in enumerate(events,2):
            cells = [book["紧急购电量"].cell(i,c).value for c in (1,2,3)]
            if str(cells[0].date())!=event["date"] or cells[1]!=event["interval"] or abs(cells[2]-event["emergency_purchase_kwh"])>1e-6:
                raise ValueError("Q4紧急区间无法由实际e独立复算")
    finally:
        book.close()


def write_submission(root, variant, human_approved=False):
    if not human_approved:
        raise ValueError("Q4全年结果尚未人工验收，禁止生成正式提交")
    folder = root/("outputs/q4/q4_2" if variant==2 else "outputs/q4/final")
    outputs,metrics = load_outputs(folder)
    if not metrics.get("formal") or metrics.get("variant")!=variant or any(s in metrics["run_label"] for s in ("REFERENCE","SMOKE")):
        raise ValueError("Q4 reference/smoke不得作为正式结果")
    validate_outputs(outputs,variant,formal=True)
    if any(file_hash(root/p)!=h for p,h in metrics["protected_sha256"].items()):
        raise ValueError("Q4全年运行后的冻结输入已变化，禁止提交")
    if variant==3:
        summary = json.loads((root/"outputs/q4/search/q4_search_summary.json").read_text(encoding="utf-8"))
        winner = [{"alpha":metrics["alpha"],"lambda":metrics["lambda"]}]
        if summary["completed_groups"]!=20 or summary["winners"]!=winner:
            raise ValueError("Q4-3必须来自动态价格20组搜索唯一winner")
        group = root/f"outputs/q4/search/groups/a{metrics['alpha']:.2f}_l{metrics['lambda']:.2f}"
        original,_ = load_outputs(group)
        for name in outputs:
            # 标签之外全部数据须与搜索winner一致，不能混入Q3或reference。
            a,b = outputs[name].drop(columns="run_label",errors="ignore"),original[name].drop(columns="run_label",errors="ignore")
            pd.testing.assert_frame_equal(a,b,atol=1e-6,rtol=0)
    destination = root/f"outputs/submissions/result4-{variant}.xlsx"
    if destination.resolve()!=root.resolve()/f"outputs/submissions/result4-{variant}.xlsx":
        raise ValueError("Q4提交路径指向了非指定目录")
    result = render_copy(root/f"data/raw/附件5/result4-{variant}.xlsx",destination,outputs,variant)
    from src.q3.search_runner import save_json
    save_json(folder/"q4_submission_validation.json",result)
    return result
