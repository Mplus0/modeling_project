"""只读生成论文检验表：仅纳入完整验收的消融，不读取Q4-A部分轨迹。"""

import json
import pandas as pd

from src.analysis.model_validation import (DETAILS, VALIDATION_TOL, common_metrics, q2_validation,
                                         q3_validation, read_csv, save_json)


def write_paper_outputs(root):
    base = root / "outputs/model_validation"
    directory = base / "summary"
    directory.mkdir(parents=True, exist_ok=True)
    rows, acceptance = [], {}
    for question, stem, labels in (("Q2", "q2_risk_ablation", ("Q2-A", "Q2-B")),
                                  ("Q3", "q3_confidence_ablation", ("Q3-C", "Q3-D"))):
        folder = base / stem
        marker = folder / "run/attempt.json"
        attempt = json.loads(marker.read_text(encoding="utf-8")) if marker.exists() else {}
        if attempt.get("status") != "validated":
            acceptance[question] = dict(passed=False, status="awaiting complete annual validation")
            continue
        # 重新校验磁盘轨迹；不因文件名或历史状态标记存在就认定结果有效。
        if question == "Q2":
            outputs, checked = q2_validation(folder / "run", root / "outputs/q2")
            reference = {k:read_csv(root / f"outputs/q2/q2_{k}.csv") for k in ("actual_schedule", "daily_metrics")}
        else:
            outputs = {k:read_csv(folder / f"run/q3_{k}.csv") for k in DETAILS}
            reference = {k:read_csv(root / f"outputs/q3/final/q3_{k}.csv") for k in DETAILS}
            checked = q3_validation(outputs)
            q3_validation(reference)
        acceptance[question] = checked
        a, b = common_metrics(outputs, question=="Q2"), common_metrics(reference, question=="Q2")
        for key, value in a.items():
            # 降低率仅为数值变化方向，SOC没有“越低越好”的预设。
            rate = None if abs(value)<=VALIDATION_TOL else (value-b[key])/value*100
            rows.append(dict(experiment=question, metric=key, ablation_model=labels[0], formal_model=labels[1],
                             ablation=value, formal=b[key], difference=b[key]-value,
                             relative_change_percent=None if rate is None else -rate,
                             reduction_percent=None if key=="final_soc_kwh" else rate))
    table = pd.DataFrame(rows, columns=["experiment", "metric", "ablation_model", "formal_model", "ablation",
                                       "formal", "difference", "relative_change_percent", "reduction_percent"])
    table.to_csv(directory / "paper_ablation_comparison.csv", index=False, encoding="utf-8-sig")
    table.to_json(directory / "paper_ablation_comparison.json", orient="records", force_ascii=False, indent=2, double_precision=15)
    save_json(directory / "paper_ablation_acceptance.json", acceptance)
    lines = ["# 模型检验论文摘要", "", "正式定量比较仅使用完整334天验收结果。日费用标准差采用总体标准差（ddof=0）。", ""]
    for question in ("Q2", "Q3"):
        if not acceptance[question]["passed"]:
            lines += [f"{question}消融的全年验收材料尚待补齐，当前不报告A/B比较值及改善率。", ""]
            continue
        subset = table[table.experiment.eq(question)]
        lines += [f"## {question}全年消融", "", "| 指标 | 消融模型 | 正式模型 | 差值（正式−消融） | 指标降低率% |", "|---|---:|---:|---:|---:|"]
        for row in subset.itertuples():
            rate = "—" if pd.isna(row.reduction_percent) else f"{row.reduction_percent:.4f}"
            lines.append(f"| {row.metric} | {row.ablation:.4f} | {row.formal:.4f} | {row.difference:.4f} | {rate} |")
        lines += ["", "指标降低率=(消融−正式)/消融×100%；负数表示增加，零基准记空值，不把所有变化自动称为改善。", ""]
    if acceptance["Q3"]["passed"]:
        lines += ["Q3正式可信度融合较直接替换预测降低全年总费用与调整费用，同时日费用波动和有效紧急购电时段数下降。紧急购电总量及费用有所增加，紧急购电天数不变，需结合单次缺口规模与调整策略解释，不能声称所有风险指标均改善。", "",
                  "此结果支持在本年度、既定参数与执行机制下可信度融合的经济作用；不能外推为所有年份的普遍优势或独立的统计显著性结论。", ""]
    lines += ["Q3 Vdk：external validated diagnostic，等待最终分支整理；不在本分支填入未取得的数值。", "",
              "Q4继续采用既有0.85/0.25的334天验收结果。价格盲消融未形成有效全年实验结果，不纳入正式定量比较。", "",
              "当前材料可支撑已完成Q3消融的年度结果分析；Q2全年消融验收及Vdk材料归并完成前，不能宣称两组消融均已验证。", ""]
    (directory / "model_validation_paper_summary.md").write_text("\n".join(lines), encoding="utf-8")
    # 技术错误保留在原JSON审计记录；论文摘要仅说明比较范围。
    (base / "q4_price_blind/q4_price_blind_paper_summary.md").write_text(
        "# Q4模型检验范围\n\n价格盲消融未形成有效全年实验结果，不纳入正式定量比较。Q4-3继续使用既有alpha=0.85、lambda=0.25的334天验收结果。\n", encoding="utf-8")
    return acceptance
