"""最终轨迹上的固定合同反事实；全部预测、场景及物理约束复用冻结Q3。"""

import json
from pathlib import Path
from types import FunctionType
from time import perf_counter
from datetime import timedelta
import numpy as np
import pandas as pd
from pyscipopt import Model
from src.common.data_loader import file_hash
from src.q2.forecasting import load_daily_inputs
from src.q3.annual import HistoricalCache, FORMAL_DATES
from src.q3.forecast import load_hourly_forecasts, update_pv
from src.q3.scenarios import build_scenarios
from src.q3.optimizer import solve_plan, VALIDATION_TOL
from src.q3.search_runner import save_json

ALPHA, WEIGHT = .85,.25
HOURS = (6,12,18)
BOUNDARY = "本实验只能评价附件实际提供的06:00、12:00、18:00新增预测；对其他发布时间，缺少独立预测数据，无法在不增加额外假设的条件下进行同等级定量评价。"


class FixedAdjustmentModel(Model):
    def addVar(self, name="", *args, **kwargs):
        # 原模型u/v下界为0，仅此诊断将上界也设0，recourse变量完全保留。
        if name.startswith(("u_","v_")):
            kwargs["ub"] = 0.
        return super().addVar(name,*args,**kwargs)


def solve_fixed_grid_diagnostic(load, pv, price, soc, previous):
    # 局部绑定模型构造器，不修改冻结模块全局变量、不复制约束或目标公式。
    solver = FunctionType(solve_plan.__code__,dict(solve_plan.__globals__,Model=FixedAdjustmentModel),
                          argdefs=solve_plan.__defaults__)
    result = solver(load,pv,price,soc,ALPHA,WEIGHT,previous)
    close(result["grid"],previous,"fixed合同")
    close(result["increase"],0.,"fixed增购")
    close(result["decrease"],0.,"fixed减购")
    close(result["purchase_or_adjustment_cost"],0.,"fixed调整费")
    return result


def close(a,b,name):
    delta = float(np.max(np.abs(np.asarray(a)-np.asarray(b))))
    if not np.isfinite(delta) or delta>VALIDATION_TOL:
        raise ValueError(f"{name}不一致：max_difference={delta}")
    return delta


def classify(value):
    return "unexpected_negative" if value < -VALIDATION_TOL else "positive" if value>VALIDATION_TOL else "numerical_zero"


def require_value(value):
    if not np.isfinite(value):
        raise ValueError("信息价值必须为有限数值")
    if classify(value)=="unexpected_negative":
        raise ValueError(f"J_roll显著超过J_fix：V={value}")


def previous_contract(plans, hour):
    previous = plans[plans.update_time.eq(f"{hour-6:02d}:00")&plans.slot.ge(hour*6+1)]
    current = plans[plans.update_time.eq(f"{hour:02d}:00")]
    expected = list(range(hour*6+1,145))
    if previous.slot.tolist()!=expected or current.slot.tolist()!=expected:
        raise ValueError("上一轮有效合同或当前计划slot不完整")
    values = previous.new_plan_kwh.to_numpy(float)
    close(values,current.previous_plan_kwh,"上一轮合同")
    return values,current


def read_final(root):
    folder = root/"outputs/q3/final"
    metrics = json.loads((folder/"q3_annual_metrics.json").read_text(encoding="utf-8"))
    if (metrics.get("run_label"),metrics.get("alpha"),metrics.get("lambda"))!=("Q3 FINAL",ALPHA,WEIGHT):
        raise ValueError("必须读取Q3 FINAL alpha=0.85 lambda=0.25")
    if (metrics["formal_start_date"],metrics["formal_end_date"],metrics["days"],metrics["slots"])!=("2025-02-01","2025-12-31",334,48096):
        raise ValueError("最终结果时间范围不完整")
    tables = {name:pd.read_csv(folder/f"q3_{name}.csv",float_precision="round_trip")
              for name in ("actual_schedule","plan_updates","forecast_updates","scenarios_summary")}
    for name,frame in tables.items():
        for column,expected in (("alpha",ALPHA),("lambda",WEIGHT),("run_label","Q3 FINAL")):
            if column in frame and not frame[column].eq(expected).all():
                raise ValueError(f"正式{name}的{column}与最终参数/标签不符")
    actual = tables["actual_schedule"]
    if len(actual)!=48096 or actual.duplicated(["date","slot"]).any() or actual.date.drop_duplicates().tolist()!=list(map(str,FORMAL_DATES)):
        raise ValueError("正式轨迹必须为完整334天48096slot")
    if not actual.run_label.eq("Q3 FINAL").all():
        raise ValueError("轨迹不是Q3 FINAL")
    return tables


def summarize(table):
    rows = []
    for hour,group in table.groupby("update_time",sort=True):
        positive = int(group.classification.eq("positive").sum())
        relative = group.relative_value_percent.dropna()
        rows.append(dict(update_time=hour,count=len(group),positive_count=positive,positive_ratio=positive/len(group),
                         zero_count=int(group.classification.eq("numerical_zero").sum()),
                         unexpected_negative_count=int(group.classification.eq("unexpected_negative").sum()),
                         mean_V_yuan=float(group.V_yuan.mean()),median_V_yuan=float(group.V_yuan.median()),
                         min_V_yuan=float(group.V_yuan.min()),max_V_yuan=float(group.V_yuan.max()),sum_V_yuan=float(group.V_yuan.sum()),
                         mean_relative_value_percent=float(relative.mean()) if len(relative) else None,
                         median_relative_value_percent=float(relative.median()) if len(relative) else None,
                         mean_J_fix_yuan=float(group.J_fix_yuan.mean()),mean_J_roll_yuan=float(group.J_roll_yuan.mean()),
                         mean_rho=float(group.confidence_rho.mean())))
    return pd.DataFrame(rows)


def run(root, limit=None):
    root = Path(root)
    target = root/"outputs/q3/diagnostics/information_value"
    if limit is not None:
        if not 1<=limit<=1002:
            raise ValueError("诊断条数必须为1至1002")
        target = target/"smoke"
    target.mkdir(parents=True,exist_ok=True)
    # 保护正式结果与源码；新诊断目录单独排除，不覆盖原论文摘要或提交。
    folders = ("data","src/q1","src/q2","src/q3","outputs/q1","outputs/q2","outputs/q3","outputs/submissions")
    paths = [p for name in folders for p in (root/name).rglob("*") if p.is_file()
             and "__pycache__" not in p.parts and not p.is_relative_to(root/"outputs/q3/diagnostics/information_value")]
    before = {str(p.relative_to(root)):file_hash(p) for p in paths}
    rows,maximum = [],0.
    tick = perf_counter()
    context = {}
    try:
        tables = read_final(root)
        history,price = load_daily_inputs(root/"data/processed/historical_power.csv",root/"data/processed/q1_input.csv")
        issues = load_hourly_forecasts(root/"data/processed/pv_forecast_hourly.csv")
        cache = HistoricalCache(history,issues)
        grouped = {key:dict(tuple(frame.groupby("date",sort=False))) for key,frame in tables.items()}
        for day in FORMAL_DATES:
            label = str(day)
            actual,plans,forecasts,scenes = [grouped[k][label] for k in tables]
            if actual.slot.tolist()!=list(range(1,145)):
                raise ValueError("正式日轨迹slot不完整")
            load,records,residuals = cache.prepare(day)
            maximum = max(maximum,close(load,actual.load_forecast_kwh,"重建负荷预测"))
            pv = None
            for hour in (0,*HOURS):
                context = dict(date=label,update_time=f"{hour:02d}:00")
                start = hour*6
                # 只读取正式轨迹中的当前已揭示锚点，不把未来真实曲线传入预测/求解器。
                anchor = history[day-timedelta(days=1)]["pv"][-1]*6 if hour==0 else actual.pv_actual_kwh.iloc[start-1]*6
                pv,raw,conf = update_pv(day,hour,anchor,pv,issues,records)
                saved_forecast = forecasts[forecasts.update_time.eq(f"{hour:02d}:00")]
                maximum = max(maximum,close(pv[start:],saved_forecast.updated_forecast_kwh,"重建PV预测"),
                              close(raw,saved_forecast.new_raw_forecast_kwh,"重建新发布PV"))
                if hour==0:
                    continue
                previous,current = previous_contract(plans,hour)
                soc = float(actual.soc_real_start_kwh.iloc[start])
                maximum = max(maximum,close(current.initial_soc_kwh,soc,"正式当前SOC"))
                scenario = build_scenarios(day,hour,load,pv,residuals,start+1)
                saved_scene = scenes[scenes.update_time.eq(f"{hour:02d}:00")]
                if list(map(str,scenario["dates"]))!=saved_scene.history_date.tolist() or any(d>=day for d in scenario["dates"]):
                    raise ValueError("历史场景日期与正式结果不一致")
                maximum = max(maximum,close(scenario["probability"],saved_scene.probability,"场景概率"),
                              close(scenario["probability"].sum(),1.,"场景概率和"))
                roll = solve_plan(scenario["load"],scenario["pv"],price[start:],soc,ALPHA,WEIGHT,previous)
                stored = float(current.primary_objective.iloc[0])
                diff = close(roll["primary_objective"],current.primary_objective,"重建J_roll与正式一级目标")
                maximum = max(maximum,diff)
                # 一致性通过后才求fixed；原求解器全部物理约束与recourse保持原样。
                fixed = solve_fixed_grid_diagnostic(scenario["load"],scenario["pv"],price[start:],soc,previous)
                jfix = fixed["primary_objective"]
                value = jfix-stored
                record = dict(**context,alpha=ALPHA,**{"lambda":WEIGHT},current_soc_kwh=soc,
                    previous_contract_total_kwh=float(previous.sum()),scenario_count=len(scenario["dates"]),
                    J_fix_yuan=jfix,J_roll_yuan=stored,V_yuan=value,
                    relative_value_percent=value/abs(jfix)*100 if abs(jfix)>VALIDATION_TOL else None,
                    relative_value_reason="defined" if abs(jfix)>VALIDATION_TOL else "abs(J_fix)<=VALIDATION_TOL",
                    fixed_expected_emergency_cost_yuan=fixed["expected_emergency_cost"],fixed_cvar_yuan=fixed["cvar_auxiliary"],
                    roll_adjustment_cost_yuan=roll["purchase_or_adjustment_cost"],roll_expected_emergency_cost_yuan=roll["expected_emergency_cost"],
                    roll_cvar_yuan=roll["cvar_auxiliary"],roll_increase_kwh=float(roll["increase"].sum()),roll_decrease_kwh=float(roll["decrease"].sum()),
                    confidence_rho=conf["confidence_rho"],classification=classify(value),
                    reconstructed_J_roll_difference=diff,fixed_max_violation=fixed["max_violation"],roll_max_violation=roll["max_violation"],
                    fixed_primary_status=fixed["primary_status"],fixed_secondary_status=fixed["secondary_status"],
                    roll_primary_status=roll["primary_status"],roll_secondary_status=roll["secondary_status"])
                rows.append(record)
                require_value(value)
                if len(rows)%100==0 or len(rows)==(limit or 1002):
                    print(f"Q3 information value {len(rows)}/{limit or 1002}",flush=True)
                if limit and len(rows)>=limit:
                    break
            if limit and len(rows)>=limit:
                break
        table = pd.DataFrame(rows)
        if len(table)!=(limit or 1002) or table.duplicated(["date","update_time"]).any():
            raise ValueError("诊断记录数或唯一性不符")
        summary = summarize(table)
        table.to_csv(target/"q3_information_value_by_update.csv",index=False,encoding="utf-8-sig")
        summary.to_csv(target/"q3_information_value_summary.csv",index=False,encoding="utf-8-sig")
        overall = dict(total_update_count=len(table),positive_update_count=int(table.classification.eq("positive").sum()),
                       positive_update_ratio=float(table.classification.eq("positive").mean()),total_information_value_yuan=float(table.V_yuan.sum()),
                       mean_information_value_yuan=float(table.V_yuan.mean()),median_information_value_yuan=float(table.V_yuan.median()),
                       unexpected_negative_count=int(table.classification.eq("unexpected_negative").sum()),
                       value_by_hour=dict(zip(summary.update_time,summary.sum_V_yuan)),runtime_seconds=perf_counter()-tick,
                       max_reconstructed_J_roll_difference=float(table.reconstructed_J_roll_difference.max()),
                       alpha=ALPHA,**{"lambda":WEIGHT},scope="SMOKE" if limit else "1002 FINAL-TRAJECTORY DIAGNOSTICS",interpretation_boundary=BOUNDARY)
        save_json(target/"q3_information_value.json",overall)
        unchanged = all(file_hash(root/p)==h for p,h in before.items())
        if not unchanged:
            raise RuntimeError("正式文件SHA-256发生变化")
        save_json(target/"q3_information_value_validation.json",dict(passed=True,records=len(table),max_reconstruction_difference=maximum,
                  sha256_unchanged=unchanged,sha256=before,tolerance=VALIDATION_TOL))
        text = ["# Q3新增预测经济信息价值诊断", "", "V=J_fix−J_roll。两者使用同一正式状态、新预测、历史场景和成本边界；fixed只固定上一轮有效合同，场景recourse自由优化。", "",
                "J_roll为已保存正式一级目标并经重建核对；两目标均不包含沉没购电费用或二级吞吐量。", "",
                "| 时刻 | 次数 | 平均V/元 | 中位数V/元 | V合计/元 | 正价值比例 |", "|---|---:|---:|---:|---:|---:|"]
        for r in summary.itertuples():
            text.append(f"| {r.update_time} | {r.count} | {r.mean_V_yuan:.6f} | {r.median_V_yuan:.6f} | {r.sum_V_yuan:.6f} | {r.positive_ratio:.2%} |")
        text.extend(["",f"全部{len(table)}次：V合计{overall['total_information_value_yuan']:.6f}元，平均{overall['mean_information_value_yuan']:.6f}元；正价值比例{overall['positive_update_ratio']:.2%}，显著负值{overall['unexpected_negative_count']}次。", "",
                     "合计V是各更新时刻局部反事实价值之和，未来时域存在重叠，不等同于可直接相加的全年实际节省费用。", "",BOUNDARY])
        (target/"q3_information_value_paper_summary.md").write_text("\n".join(text)+"\n",encoding="utf-8")
        print(summary[["update_time","mean_V_yuan","median_V_yuan","sum_V_yuan","positive_ratio"]].to_string(index=False),flush=True)
        print(json.dumps(overall,ensure_ascii=False,indent=2),flush=True)
        return table,overall
    except Exception as error:
        if rows:
            pd.DataFrame(rows).to_csv(target/"q3_information_value_partial.csv",index=False,encoding="utf-8-sig")
        save_json(target/"q3_information_value_failure.json",dict(**context,error=str(error),completed_records=len(rows)))
        raise
    finally:
        if any(file_hash(root/p)!=h for p,h in before.items()):
            raise RuntimeError("诊断前后正式文件SHA-256不一致")
