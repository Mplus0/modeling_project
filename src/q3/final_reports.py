"""从最终已验收数据整理论文交接结果，不重新评分或添加建模解释。"""

import pandas as pd

from src.q3.optimizer import VALIDATION_TOL


def comparison_table(q2, q3):
    mapping = [("total_actual_cost_yuan","total_actual_cost_yuan"),("total_emergency_purchase_kwh","total_emergency_purchase_kwh"),
               ("total_emergency_cost_yuan","total_emergency_cost_yuan"),("emergency_slot_count","emergency_purchase_slot_count"),
               ("emergency_day_count","emergency_purchase_day_count"),("initial_soc_kwh","initial_soc_kwh"),
               ("final_soc_kwh","final_soc_kwh"),("average_day_end_soc_kwh","average_day_end_soc_kwh"),
               ("simultaneous_slots","simultaneous_actual_charge_discharge_slots")]
    rows = []
    for key,q2key in mapping:
        if q2key in q2:
            rows.append((key,float(q2[q2key]),float(q3[key])))
    rows.append(("max_constraint_violation",max(float(q2[k]) for k in ("maximum_plan_constraint_violation","maximum_actual_constraint_violation","maximum_rolling_constraint_violation")),float(q3["max_constraint_violation"])))
    # 差值统一为Q3-Q2；零基准的百分比没有定义，保留为空并在文字中解释。
    return pd.DataFrame([dict(metric=key,q2=a,q3=b,absolute_difference=b-a,
                               percentage_change=None if abs(a)<=VALIDATION_TOL else (b-a)/a*100) for key,a,b in rows])


def markdown_table(frame):
    def show(value):
        if pd.isna(value):
            return "不适用"
        if isinstance(value,(int,float)):
            return f"{0. if abs(value)<=VALIDATION_TOL else value:.6f}"
        return str(value)
    lines = ["| "+" | ".join(map(str,frame.columns))+" |","| "+" | ".join(["---"]*len(frame.columns))+" |"]
    lines.extend("| "+" | ".join(show(v) for v in row)+" |" for row in frame.itertuples(index=False,name=None))
    return "\n".join(lines)


def write_paper_reports(directory, outputs, metrics, ranking, selection, q2, submission_status, todos):
    comparison = comparison_table(q2,metrics)
    comparison.to_csv(directory/"q2_vs_q3_final_comparison.csv",index=False,encoding="utf-8-sig")
    comparison_text = "# Q2与最终Q3结果比较\n\n差值为Q3−Q2；百分比基准为Q2，零基准记为不适用。\n\n"+markdown_table(comparison)+"\n"
    (directory/"q2_vs_q3_final_comparison.md").write_text(comparison_text,encoding="utf-8")
    daily = outputs["daily_metrics"]
    updates = pd.DataFrame([dict(update_time=f"{h:02d}:00",rho_mean=float(daily[f"rho_{h:02d}"].mean()),
                                 increase_kwh=float(daily[f"increase_{h:02d}_kwh"].sum()),
                                 decrease_kwh=float(daily[f"decrease_{h:02d}_kwh"].sum())) for h in (6,12,18)])
    updates.to_csv(directory/"q3_update_time_summary.csv",index=False,encoding="utf-8-sig")
    columns = ["alpha","lambda","total_cost","emergency_slot_count","daily_cost_std","Score"]
    table = ranking[columns].copy()
    table["winner"] = table.alpha.eq(metrics["alpha"])&table["lambda"].eq(metrics["lambda"])
    table.to_csv(directory/"q3_parameter_selection_table.csv",index=False,encoding="utf-8-sig")
    keys = ("total_actual_cost_yuan","total_plan_cost_00_yuan","total_adjustment_cost_yuan","total_emergency_purchase_kwh",
            "total_emergency_cost_yuan","emergency_slot_count","emergency_day_count","daily_cost_std_yuan", "initial_soc_kwh",
            "final_soc_kwh","minimum_soc_kwh","maximum_soc_kwh","average_day_end_soc_kwh","days_ending_near_soc_min",
            "max_constraint_violation","cross_day_soc_max_difference","simultaneous_slots")
    lines = ["# Q3最终结果交接", "",f"最终参数alpha={metrics['alpha']}、lambda={metrics['lambda']}。",
             f"20组联合全年实验在统一Min-Max及0.5/0.3/0.2权重下比较，唯一winner的Score={selection['best_score']}。",
             "这是在当前候选网格与当前评价体系下的最优参数，不是唯一理论最优参数。", "",
             "334天、48096个实际执行时段；最终完整重跑已通过年度独立验收及与搜索winner的逐值对比。", "",
             markdown_table(pd.DataFrame([dict(metric=k,value=metrics[k]) for k in keys])), "",
             "## 预测更新汇总", "",markdown_table(updates), "",comparison_text,
             "## 求解状态", "",str(metrics["solver_status_counts"]), "",
             f"result3.xlsx状态：{submission_status}", "", "待确认事项："+("；".join(todos) if todos else "无"), "",
             "## 可直接引用的数据说明", "",
             "模型利用00:00、06:00、12:00和18:00四个预测发布时刻进行滚动更新。由于附件未提供其他发布时间的独立预测版本，无法在不引入额外假设的情况下对其他时刻进行同等级定量评估。",
             "SOC低位运行按已确认模型如实保留，未增加终端恢复或储能储备目标。"]
    for key,description in (("total_actual_cost_yuan","总实际费用"),("total_emergency_purchase_kwh","紧急购电量"),("total_emergency_cost_yuan","紧急购电费用")):
        row = comparison[comparison.metric.eq(key)].iloc[0]
        lines.append(f"相较Q2，Q3{description}变化{row.percentage_change:.4f}%。")
    text = "\n".join(lines)+"\n"
    (directory/"q3_paper_summary.md").write_text(text,encoding="utf-8")
    (directory/"q3_final_summary.md").write_text(text,encoding="utf-8")
