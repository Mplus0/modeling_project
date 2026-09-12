"""团队确认winner的最终运行门槛、标签与搜索一致性复核。"""

import json
import math

import numpy as np
import pandas as pd

from src.q3.annual import ANNUAL_LABEL, validate_annual
from src.q3.parameters import PARAMETER_GRID
from src.q3.optimizer import VALIDATION_TOL
from src.q3.search_runner import validate_group, DETAIL_NAMES

FINAL_ALPHA = .85
FINAL_LAMBDA = .25
FINAL_LABEL = "Q3 FINAL"


def read_confirmed_selection(root):
    """读取冻结排名并核对团队已指定winner，绝不重新评分或选参。"""
    search = root/"outputs/q3/search"
    summary = json.loads((search/"q3_parameter_search_summary.json").read_text(encoding="utf-8"))
    ranking = pd.read_csv(search/"q3_parameter_ranking.csv",float_precision="round_trip")
    if (summary["completed_groups"]!=20 or summary["failed_groups"] or not summary["all_groups_valid"]
            or summary["winner_count"]!=1 or summary["winners"]!=[{"alpha":FINAL_ALPHA,"lambda":FINAL_LAMBDA}]):
        raise ValueError("Q3冻结搜索未确认唯一指定winner，禁止最终运行")
    if len(ranking)!=20 or set(zip(ranking.alpha,ranking["lambda"]))!=set(PARAMETER_GRID):
        raise ValueError("Q3冻结排名不是完整20组")
    if not np.isfinite(ranking.select_dtypes(include=[np.number]).to_numpy()).all():
        raise ValueError("Q3冻结排名存在缺失或非有限数值")
    winners = ranking[ranking.Score.eq(ranking.Score.min())]
    if len(winners)!=1 or (float(winners.alpha.iloc[0]),float(winners["lambda"].iloc[0]))!=(FINAL_ALPHA,FINAL_LAMBDA):
        raise ValueError("Q3冻结排名与团队指定winner不一致")
    if abs(float(winners.Score.iloc[0])-summary["best_score"])>1e-12:
        raise ValueError("Q3冻结Score摘要与排名不一致")
    group = search/f"groups/a{FINAL_ALPHA:.2f}_l{FINAL_LAMBDA:.2f}"
    daily = pd.read_csv(group/"q3_daily_metrics.csv",float_precision="round_trip")
    metrics = json.loads((group/"q3_annual_metrics.json").read_text(encoding="utf-8"))
    validate_group(daily,metrics,FINAL_ALPHA,FINAL_LAMBDA)
    return ranking,summary,daily,metrics


def compare_search_winner(daily, metrics, search_daily, search_metrics):
    differences, failures = {}, []
    if len(daily)!=334 or daily.date.tolist()!=search_daily.date.tolist():
        return dict(passed=False,tolerance=VALIDATION_TOL,failures=["日期/行数不一致"],differences={})
    for column in search_daily:
        if column=="run_label":
            continue
        if column not in daily:
            failures.append(f"缺少逐日列:{column}")
        elif pd.api.types.is_numeric_dtype(search_daily[column]):
            values = daily[column].to_numpy(float)-search_daily[column].to_numpy(float)
            delta = float(np.max(np.abs(values)))
            differences[f"daily.{column}"] = delta if math.isfinite(delta) else None
            if not math.isfinite(delta) or delta>VALIDATION_TOL:
                failures.append(f"逐日数值不一致:{column}")
        elif daily[column].astype(str).tolist()!=search_daily[column].astype(str).tolist():
            failures.append(f"逐日字段不一致:{column}")
    # 时间计量、验收来源与运行标签不属于数学结果；其余年度数值逐项复核。
    ignored = {"run_label","integrity","search_validation","solver_status_counts","preparation_scope"}
    for key,value in search_metrics.items():
        if key in ignored or key.endswith("seconds"):
            continue
        if key not in metrics:
            failures.append(f"缺少年度字段:{key}")
        elif isinstance(value,(int,float)) and not isinstance(value,bool):
            delta = abs(float(metrics[key])-value)
            differences[f"annual.{key}"] = delta if math.isfinite(delta) else None
            if not math.isfinite(delta) or delta>VALIDATION_TOL:
                failures.append(f"年度数值不一致:{key}")
        elif metrics[key]!=value:
            failures.append(f"年度字段不一致:{key}")
    if metrics.get("solver_status_counts")!=search_metrics.get("solver_status_counts"):
        failures.append("年度求解状态计数不一致")
    return dict(passed=not failures,tolerance=VALIDATION_TOL,failures=failures,differences=differences,
                max_absolute_difference=max((v for v in differences.values() if v is not None),default=0.))


def validate_final(outputs, metrics):
    if metrics["run_label"]!=FINAL_LABEL or (metrics["alpha"],metrics["lambda"])!=(FINAL_ALPHA,FINAL_LAMBDA):
        raise ValueError("Q3最终标签或固定参数不符")
    # 原年度验证器仍保持冻结；只在验证视图中适配标签，不改CSV或模型。
    view = dict(outputs)
    for key in ("daily_metrics","actual_schedule"):
        if not outputs[key].run_label.eq(FINAL_LABEL).all():
            raise ValueError("Q3最终明细混入参考标签")
        view[key] = outputs[key].assign(run_label=ANNUAL_LABEL)
    result = validate_annual(view)
    if metrics["simultaneous_slots"]!=0 or not outputs["daily_metrics"].simultaneous_slots.eq(0).all():
        raise ValueError("Q3最终有效同时充放电不为0")
    validate_group(view["daily_metrics"],dict(metrics,run_label=ANNUAL_LABEL),FINAL_ALPHA,FINAL_LAMBDA)
    return dict(result,passed=True,days=334,slots=48096,run_label=FINAL_LABEL)


def load_final(directory):
    outputs = {key:pd.read_csv(directory/f"q3_{key}.csv",float_precision="round_trip") for key in DETAIL_NAMES}
    metrics = json.loads((directory/"q3_annual_metrics.json").read_text(encoding="utf-8"))
    return outputs,metrics
