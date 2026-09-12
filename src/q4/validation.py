"""对实际轨迹、价格信息集、合同更新及真实结算进行独立复算。"""

import numpy as np
import pandas as pd
from src.q2.optimizer import validate_schedule, VALIDATION_TOL
from src.q3.annual import validate_annual, FORMAL_DATES, ANNUAL_LABEL
from src.q4.price_forecasting import PRICE_EPSILON


def validate_outputs(outputs, variant, formal=False):
    actual,daily = outputs["actual_schedule"],outputs["daily_metrics"]
    expected = list(map(str,FORMAL_DATES)) if formal else list(map(str,pd.date_range(daily.date.iloc[0],daily.date.iloc[-1]).date))
    if daily.date.tolist()!=expected or len(actual)!=144*len(expected) or actual.duplicated(["date","slot"]).any():
        raise ValueError("Q4日期、记录数或唯一性不符")
    for key,frame in outputs.items():
        if frame.isna().any().any() or not np.isfinite(frame.select_dtypes(include=[np.number]).to_numpy()).all():
            raise ValueError(f"Q4 {key}存在缺失或非有限值")
    for stage in ("primary","secondary","tertiary"):
        if not actual[f"rolling_{stage}_status"].eq("optimal").all():
            raise ValueError("Q4实际求解未全部optimal")
    plans = outputs["plan_schedule" if variant==2 else "plan_updates"]
    if not plans[["primary_status","secondary_status"]].eq("optimal").all().all():
        raise ValueError("Q4计划求解未全部optimal")
    maximum,cross,soc = 0.,0.,6000.
    def check(a,b):
        nonlocal maximum
        maximum = max(maximum,float(np.max(np.abs(np.asarray(a)-np.asarray(b)))))
    for row in daily.itertuples():
        a = actual[actual.date.eq(row.date)]
        refresh = outputs["price_refresh"][outputs["price_refresh"].date.eq(row.date)]
        if a.slot.tolist()!=list(range(1,145)) or refresh.slot.tolist()!=list(range(1,145)):
            raise ValueError("Q4每日slot或价格刷新序列不完整")
        cross = max(cross,abs(row.soc_start_kwh-soc))
        verified = validate_schedule(a,"actual",soc)
        maximum = max(maximum,verified["max_violation"],float(a.rolling_max_violation.max()),row.max_constraint_violation)
        check(row.soc_end_kwh,a.soc_real_end_kwh.iloc[-1])
        soc = row.soc_end_kwh
        price = a.price_yuan_per_kwh.to_numpy()
        baseline = refresh.baseline_price_yuan_per_kwh.to_numpy()
        if (price<0).any() or (baseline<0).any():
            raise ValueError("Q4价格不可为负")
        check(refresh.gamma,np.cumsum(price)/(np.cumsum(baseline)+PRICE_EPSILON))
        check(refresh.observed_count,np.arange(1,145))
        check(refresh.observed_price_sum,np.cumsum(price))
        check(refresh.baseline_observed_sum,np.cumsum(baseline))
        select = outputs["price_selection"][outputs["price_selection"].date.eq(row.date)]
        if len(select)!=1 or select.chosen_price_window_weeks.iloc[0] not in (1,2,3,4):
            raise ValueError("Q4每日动态价格选窗不完整")
        backtests = select.price_backtest_dates.iloc[0].split("|")
        if any(d>=row.date for d in backtests) or len(backtests)!=select.price_backtest_days.iloc[0]:
            raise ValueError("Q4价格回测含未来日期或样本数不符")
        p = plans[plans.date.eq(row.date)]
        if variant==2:
            if p.slot.tolist()!=list(range(1,145)):
                raise ValueError("Q4-2计划slot不完整")
            verified_plan = validate_schedule(p,"plan",row.soc_start_kwh)
            maximum = max(maximum,verified_plan["max_violation"])
            check(p.price_yuan_per_kwh,baseline)
            check(a.grid_purchase_plan_kwh,p.grid_purchase_plan_kwh)
            planned = float(price@p.grid_purchase_plan_kwh)
            adjustment = 0.
        else:
            if p.update_time.drop_duplicates().tolist()!=["00:00","06:00","12:00","18:00"]:
                raise ValueError("Q4-3合同更新时刻不符")
            planned = float(price@p[p.update_time.eq("00:00")].new_plan_kwh)
            adjustment = 0.
            scenarios = outputs["scenarios_summary"]
            for hour in (0,6,12,18):
                block = p[p.update_time.eq(f"{hour:02d}:00")]
                start = hour*6
                if block.slot.tolist()!=list(range(start+1,145)):
                    raise ValueError("Q4合同调整包含已执行slot或遗漏尾部")
                gamma = 1. if hour==0 else refresh.gamma.iloc[start-1]
                check(block.price_forecast_yuan_per_kwh,gamma*baseline[start:])
                check(block.contract_gamma,gamma)
                executed = a.iloc[start:start+36]
                check(executed.grid_purchase_plan_kwh,block.new_plan_kwh.iloc[:36])
                scene = scenarios[scenarios.date.eq(row.date)&scenarios.update_time.eq(f"{hour:02d}:00")]
                if (scene.history_date>=row.date).any() or scene.history_date.duplicated().any():
                    raise ValueError("Q4场景历史信息非法")
                check(scene.probability.sum(),1.)
                target = float(scene.probability@scene.terminal_soc_kwh)
                check(block.plan_terminal_soc_kwh,target)
                check(executed.plan_terminal_soc_kwh,target)
                if hour:
                    prior = p[p.update_time.eq(f"{hour-6:02d}:00")&p.slot.gt(start)]
                    check(block.previous_plan_kwh,prior.new_plan_kwh)
                    check(block.new_plan_kwh,block.previous_plan_kwh+block.increase_kwh-block.decrease_kwh)
                    maximum = max(maximum,float(max(0.,(block.decrease_kwh-block.previous_plan_kwh).max())),
                                  float(max(0.,-block[["increase_kwh","decrease_kwh"]].min().min())))
                costs = price[start:]*(1.5*block.increase_kwh.to_numpy()-.5*block.decrease_kwh.to_numpy())
                check(block.adjustment_cost_yuan,costs)
                adjustment += float(costs.sum())
        check(row.plan_cost_00_yuan,planned)
        check(row.adjustment_cost_total_yuan,adjustment)
        check(row.actual_emergency_cost_yuan,verified["cost"])
        check(row.actual_emergency_purchase_kwh,a.emergency_purchase_kwh.sum())
        check(row.actual_throughput_kwh,verified["throughput"])
        check(row.total_actual_cost_yuan,planned+adjustment+verified["cost"])
        check(row.emergency_slot_count,int((a.emergency_purchase_kwh>VALIDATION_TOL).sum()))
        check(row.simultaneous_slots,verified["simultaneous_slots"])
    if variant==3 and formal:
        # 原Q3验收公式同样适用于真实价格结算，只适配标签视图。
        view = dict(outputs)
        for key in ("actual_schedule","daily_metrics"):
            view[key] = outputs[key].assign(run_label=ANNUAL_LABEL)
        maximum = max(maximum,validate_annual(view)["max_constraint_violation"])
    if max(maximum,cross)>VALIDATION_TOL:
        raise ValueError(f"Q4独立复算违反容差：max={maximum}, cross_day={cross}")
    return dict(passed=True,days=len(daily),slots=len(actual),max_constraint_violation=maximum,cross_day_soc_max_difference=cross)
