"""Q3参数组恢复与运行管理；物理模型、年度验收及评分均复用既有实现。"""

import json
from datetime import datetime
from pathlib import Path
from time import perf_counter

import numpy as np
import pandas as pd

from src.common.data_loader import file_hash
from src.q3.annual import FORMAL_DATES, ANNUAL_LABEL, run_dates, validate_annual
from src.q3.parameters import PARAMETER_GRID, ALPHA_CHOICES, LAMBDA_CHOICES
from src.q3.optimizer import SOC_MIN, VALIDATION_TOL
from src.q3.metrics import write_annual_outputs
from src.q3.search import score_annual_results

DETAIL_NAMES = ("forecast_updates","confidence","scenarios_summary","plan_updates","actual_schedule","daily_metrics")


def save_json(path, value):
    # JSON最后原子替换，只有完整写入的文件可被下一次恢复读取。
    temporary = path.with_suffix(path.suffix+".tmp")
    temporary.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    temporary.replace(path)


def validate_group(daily, metrics, alpha, weight):
    """摘要恢复独立检查日期、参数、结算、真实状态及完整求解状态。"""
    if (alpha,weight) not in PARAMETER_GRID or metrics["alpha"]!=alpha or metrics["lambda"]!=weight:
        raise ValueError("Q3恢复参数不一致或非法")
    if daily.date.tolist()!=[str(d) for d in FORMAL_DATES] or metrics["days"]!=334 or metrics["slots"]!=48096:
        raise ValueError("Q3恢复需要334个不重复完整日期及48096时段")
    if metrics["formal_start_date"]!="2025-02-01" or metrics["formal_end_date"]!="2025-12-31":
        raise ValueError("Q3恢复年度日期不符")
    if not daily.alpha.eq(alpha).all() or not daily["lambda"].eq(weight).all():
        raise ValueError("Q3恢复逐日参数不符")
    if metrics["run_label"]!=ANNUAL_LABEL or not daily.run_label.eq(ANNUAL_LABEL).all():
        raise ValueError("Q3恢复运行标签不符")
    if daily.isna().any().any() or not np.isfinite(daily.select_dtypes(include=[np.number]).to_numpy()).all():
        raise ValueError("Q3恢复逐日结果缺失或含非有限值")
    def finite_tree(value):
        if isinstance(value,dict):
            return all(finite_tree(v) for v in value.values())
        if isinstance(value,list):
            return all(finite_tree(v) for v in value)
        return not isinstance(value,(int,float)) or np.isfinite(value)
    if not finite_tree(metrics):
        raise ValueError("Q3恢复年度指标含非有限值")
    for col in ("max_constraint_violation","cross_day_soc_max_difference"):
        if not 0<=metrics[col]<=VALIDATION_TOL:
            raise ValueError("Q3恢复约束或跨日误差超限")
    if metrics["simultaneous_slots"]!=0 or not daily.simultaneous_slots.eq(0).all():
        raise ValueError("Q3搜索验收要求有效同时充放电为0")
    if (daily.max_constraint_violation>VALIDATION_TOL).any() or (daily.max_constraint_violation<0).any():
        raise ValueError("Q3恢复逐日约束误差超限")
    for stage in ("primary","secondary","tertiary"):
        if metrics["solver_status_counts"][f"actual_{stage}"]!={"optimal":48096} or not daily[f"actual_{stage}_status"].eq("optimal").all():
            raise ValueError("Q3恢复实际求解状态不完整")
    for stage in ("primary","secondary"):
        if metrics["solver_status_counts"][f"plan_{stage}"]!={"optimal":1336}:
            raise ValueError("Q3恢复计划求解状态不完整")
        for h in (0,6,12,18):
            if not daily[f"plan_{stage}_status_{h:02d}"].eq("optimal").all():
                raise ValueError("Q3恢复逐日计划状态不完整")
    sums = {"total_plan_cost_00_yuan":"plan_cost_00_yuan","total_adjustment_cost_yuan":"adjustment_cost_total_yuan",
            "total_emergency_cost_yuan":"actual_emergency_cost_yuan","total_actual_cost_yuan":"total_actual_cost_yuan",
            "total_emergency_purchase_kwh":"actual_emergency_purchase_kwh","emergency_slot_count":"emergency_slot_count"}
    expected = {key:float(daily[col].sum()) for key,col in sums.items()}
    expected.update(initial_soc_kwh=6000.,final_soc_kwh=float(daily.soc_end_kwh.iloc[-1]),
                    minimum_soc_kwh=float(daily.soc_min_kwh.min()),maximum_soc_kwh=float(daily.soc_max_kwh.max()),
                    daily_cost_mean_yuan=float(daily.total_actual_cost_yuan.mean()),
                    daily_cost_std_yuan=float(np.std(daily.total_actual_cost_yuan,ddof=0)),
                    emergency_day_count=int((daily.emergency_slot_count>0).sum()),
                    average_day_end_soc_kwh=float(daily.soc_end_kwh.mean()),
                    days_ending_near_soc_min=int((np.abs(daily.soc_end_kwh-SOC_MIN)<=VALIDATION_TOL).sum()))
    expected["total_increase_adjustment_kwh"] = sum(float(daily[f"increase_{h:02d}_kwh"].sum()) for h in (6,12,18))
    expected["total_decrease_adjustment_kwh"] = sum(float(daily[f"decrease_{h:02d}_kwh"].sum()) for h in (6,12,18))
    for h in (6,12,18):
        expected[f"rho_{h:02d}_mean"] = float(daily[f"rho_{h:02d}"].mean())
    if any(abs(float(metrics[k])-v)>VALIDATION_TOL for k,v in expected.items()):
        raise ValueError("Q3年度指标与逐日指标复算不一致")
    if (np.max(np.abs(daily.soc_start_kwh.to_numpy()-np.r_[6000.,daily.soc_end_kwh.to_numpy()[:-1]]))>VALIDATION_TOL
            or np.max(np.abs(daily.total_actual_cost_yuan-daily.plan_cost_00_yuan-daily.adjustment_cost_total_yuan-daily.actual_emergency_cost_yuan))>VALIDATION_TOL):
        raise ValueError("Q3逐日状态传递或结算不一致")
    if metrics["W_c"]!=7 or metrics["W_s"]!=14 or metrics["validation_tolerance"]!=VALIDATION_TOL:
        raise ValueError("Q3恢复模型窗口或容差不一致")
    return True


def read_group(folder, alpha, weight, signature):
    daily_path = folder/"q3_daily_metrics.csv"
    metrics = json.loads((folder/"q3_annual_metrics.json").read_text(encoding="utf-8"))
    stamp = metrics.get("search_validation",{})
    if stamp.get("status")!="PASSED" or stamp.get("signature")!=signature or stamp.get("daily_sha256")!=file_hash(daily_path):
        raise ValueError("Q3恢复缺少完整验收记录、数据/模型已变化或摘要文件损坏")
    daily = pd.read_csv(daily_path,float_precision="round_trip")
    validate_group(daily,metrics,alpha,weight)
    return daily,metrics


def persist_group(folder, daily, metrics, signature, source):
    folder.mkdir(parents=True,exist_ok=True)
    daily_path = folder/"q3_daily_metrics.csv"
    temp = folder/"q3_daily_metrics.csv.tmp"
    daily.to_csv(temp,index=False,encoding="utf-8-sig")
    temp.replace(daily_path)
    metrics = dict(metrics,search_validation=dict(status="PASSED",signature=signature,
                                                   daily_sha256=file_hash(daily_path),source=source))
    save_json(folder/"q3_annual_metrics.json",metrics)
    return metrics


def validate_reference(folder):
    outputs = {key:pd.read_csv(folder/f"q3_{key}.csv",float_precision="round_trip") for key in DETAIL_NAMES}
    validate_annual(outputs)
    metrics = json.loads((folder/"q3_annual_metrics.json").read_text(encoding="utf-8"))
    validate_group(outputs["daily_metrics"],metrics,.90,.50)
    return outputs["daily_metrics"],metrics


def run_search(root, history, issues, price, signature, integrity_check, runner=run_dates, grid=PARAMETER_GRID):
    """每组重新调用年度引擎，初始SOC固定6000；只持久化已验收摘要。"""
    search = root/"outputs/q3/search"
    search.mkdir(parents=True,exist_ok=True)
    reference = root/"outputs/q3/annual/reference_a0.90_l0.50"
    # 长任务前必须验收完整reference；不能仅依赖文件存在。
    reference_daily,reference_metrics = validate_reference(reference)
    started = perf_counter()
    collected, annuals, states = [], [], []
    summary_path = search/"q3_parameter_search_summary.json"
    for name in ("q3_parameter_ranking.csv","q3_parameter_ranking.json","q3_all_daily_metrics.csv"):
        (search/name).unlink(missing_ok=True)
    def status_summary():
        result = dict(candidate_alpha=list(ALPHA_CHOICES),candidate_lambda=list(LAMBDA_CHOICES),total_groups=len(PARAMETER_GRID),
                      completed_groups=sum(s["status"]=="COMPLETED" for s in states),
                      failed_groups=[s for s in states if s["status"]=="FAILED"],groups=states,
                      score_weights=dict(total_cost=.5,emergency_slot_count=.3,daily_cost_std=.2),
                      total_search_runtime_seconds=perf_counter()-started,all_groups_valid=False,
                      reused_reference_group={"alpha":.90,"lambda":.50},integrity=integrity_check())
        save_json(summary_path,result)
        return result
    status_summary()
    for number,(alpha,weight) in enumerate(grid,1):
        folder = search/f"groups/a{alpha:.2f}_l{weight:.2f}"
        if not folder.resolve().is_relative_to(search.resolve()):
            raise ValueError("Q3搜索输出路径越界")
        start_time,group_tick = datetime.now().isoformat(timespec="seconds"),perf_counter()
        print(f"[{number:02d}/{len(PARAMETER_GRID)}] alpha={alpha:.2f} lambda={weight:.2f} start={start_time}",flush=True)
        source = "computed"
        try:
            try:
                daily,metrics = read_group(folder,alpha,weight,signature)
                source = "checkpoint"
                print("SKIP / REUSE：完整组摘要校验通过",flush=True)
            except (OSError,ValueError,KeyError,TypeError) as exc:
                if folder.exists():
                    print(f"已有摘要未通过校验，将重新计算：{exc}",flush=True)
                if (alpha,weight)==(.90,.50):
                    daily,metrics = reference_daily.copy(),dict(reference_metrics)
                    source = "reference"
                else:
                    progress = lambda n,total,day: print(f"  [{number:02d}/20] {n}/{total} days: {day}",flush=True)
                    # 每次run_dates自行新建缓存和求解模型，不把上组SOC传入下一组。
                    outputs,timings = runner(history,issues,price,FORMAL_DATES,6000.,alpha,weight,progress)
                    timings["runtime_seconds"] = perf_counter()-group_tick
                    metrics = write_annual_outputs(outputs,folder,timings,integrity_check(),save_details=False)
                    daily = outputs["daily_metrics"].copy()
                    del outputs
                validate_group(daily,metrics,alpha,weight)
                metrics = persist_group(folder,daily,metrics,signature,source)
            collected.append(daily)
            annuals.append(metrics)
            state = dict(alpha=alpha,**{"lambda":weight},status="COMPLETED",source=source,start_time=start_time,
                         end_time=datetime.now().isoformat(timespec="seconds"),wall_seconds=perf_counter()-group_tick,
                         runtime_seconds=metrics["runtime_seconds"])
            states.append(state)
            print(f"完成 {number}/20 end={state['end_time']} wall={state['wall_seconds']:.2f}s run={metrics['runtime_seconds']:.2f}s cost={metrics['total_actual_cost_yuan']:.6f} emergency_slots={metrics['emergency_slot_count']} std={metrics['daily_cost_std_yuan']:.6f}",flush=True)
            status_summary()
        except Exception as exc:
            states.append(dict(alpha=alpha,**{"lambda":weight},status="FAILED",error=str(exc),start_time=start_time,
                               end_time=datetime.now().isoformat(timespec="seconds")))
            status_summary()
            raise
    all_daily = pd.concat(collected,ignore_index=True)
    # 唯一评分实现会强制检查全部20组；任何不完整集合均不能生成最终排名。
    ranking,winners = score_annual_results(all_daily)
    extra = pd.DataFrame(annuals)[["alpha","lambda","final_soc_kwh","average_day_end_soc_kwh","emergency_day_count",
                                   "total_emergency_purchase_kwh","runtime_seconds"]]
    ranking = ranking.merge(extra,on=["alpha","lambda"],validate="one_to_one")
    ranking = ranking.sort_values("Score",kind="stable").reset_index(drop=True)
    ranking.insert(0,"rank",ranking.Score.rank(method="min",ascending=True).astype(int))
    ranking.to_csv(search/"q3_parameter_ranking.csv",index=False,encoding="utf-8-sig")
    all_daily.to_csv(search/"q3_all_daily_metrics.csv",index=False,encoding="utf-8-sig")
    save_json(search/"q3_parameter_ranking.json",ranking.to_dict("records"))
    summary = status_summary()
    summary.update(all_groups_valid=True,normalization_bounds={col:dict(min=float(ranking[f"min_{col}"].iloc[0]),max=float(ranking[f"max_{col}"].iloc[0]))
                                                              for col in ("total_cost","emergency_slot_count","daily_cost_std")},
                   winner_count=len(winners),winners=winners.to_dict("records"),best_score=float(ranking.Score.min()),
                   total_search_runtime_seconds=perf_counter()-started)
    save_json(summary_path,summary)
    return summary
