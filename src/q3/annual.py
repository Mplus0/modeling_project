"""单组正式全年参考：逐日增量缓存与已验证单日引擎，禁止参数间复用SOC。"""

from datetime import timedelta
from time import perf_counter

import numpy as np
import pandas as pd

from src.q3.forecast import load_prediction, replay_completed_day
from src.q3.confidence import W_C
from src.q3.scenarios import W_S
from src.q3.simulation import simulate_day
from src.q3.parameters import ALPHA_CHOICES, LAMBDA_CHOICES
from src.q3.optimizer import VALIDATION_TOL, validate_schedule

FORMAL_DATES = tuple(pd.date_range("2025-02-01", "2025-12-31").date)
ANNUAL_LABEL = "ANNUAL REFERENCE ONLY"


class HistoricalCache:
    """缓存只保存参数无关历史；prepare(day)绝不把day及未来实测加入历史。"""

    def __init__(self, history, issues):
        self.history, self.issues = history, issues
        self.dates = sorted(history)
        self.cursor = 0
        self.prior, self.records, self.residuals = {}, {}, {}
        self.forecast_cache, self.loads = {}, {}
        self.replayed_days = 0

    def prepare(self, day):
        if self.prior and max(self.prior) >= day:
            raise ValueError("Q3年度缓存不能逆序使用或包含目标日/未来日期")
        while self.cursor < len(self.dates) and self.dates[self.cursor] < day:
            completed = self.dates[self.cursor]
            self.prior[completed] = self.history[completed]
            # 每个已完成日仅回放一次，复用原回放函数及Q2候选回测缓存。
            replay_completed_day(self.prior, completed, self.issues, self.records,
                                 self.residuals, self.forecast_cache, self.loads.get(completed))
            self.cursor += 1
            self.replayed_days += 1
        if day not in self.loads:
            self.loads[day], _ = load_prediction(self.prior, day, self.forecast_cache)
        records = {d:self.records[d] for d in sorted(self.records)[-W_C:]}
        residuals = {d:self.residuals[d] for d in sorted(self.residuals)[-W_S:]}
        return self.loads[day].copy(), records, residuals


def run_dates(history, issues, price, dates, initial_soc, alpha, risk_weight, progress=None):
    """年度与小规模等价测试共用；每次调用创建独立真实状态和历史缓存。"""
    if alpha not in ALPHA_CHOICES or risk_weight not in LAMBDA_CHOICES:
        raise ValueError("Q3年度参数不在公共候选集合中")
    dates = tuple(dates)
    if not dates or dates != tuple(pd.date_range(dates[0],dates[-1]).date):
        raise ValueError("Q3年度引擎日期必须非空、唯一且连续")
    cache = HistoricalCache(history, issues)
    rows, soc = [], float(initial_soc)
    tick, preparation, first_seven = perf_counter(), 0., None
    preparation_detail = {"forecast_scenario_seconds":0.}
    for index, day in enumerate(dates):
        prep_tick = perf_counter()
        load, records, residuals = cache.prepare(day)
        preparation += perf_counter()-prep_tick
        actual = history[day]
        # 回调逐时揭示真实观测，预测/场景接口只持有严格历史和当前发布锚点。
        result = simulate_day(day,lambda slot:(float(actual["load"][slot-1]),float(actual["pv"][slot-1])),
                              float(history[day-timedelta(days=1)]["pv"][-1])*6,
                              load,price,issues,records,residuals,soc,alpha,risk_weight,run_label=ANNUAL_LABEL,timings=preparation_detail)
        result["actual_schedule"]["source_time"] = actual["source_time"]
        end = float(result["actual_schedule"].soc_real_end_kwh.iloc[-1])
        if abs(float(result["daily_metrics"].soc_start_kwh.iloc[0])-soc)>VALIDATION_TOL:
            raise RuntimeError("Q3跨日真实SOC传递失败")
        soc = end
        rows.append(result)
        if index == 6:
            first_seven = perf_counter()-tick
        if progress and ((index+1)%10 == 0 or index+1 == len(dates)):
            progress(index+1,len(dates),day)
    outputs = {key:pd.concat([r[key] for r in rows],ignore_index=True) for key in rows[0]}
    timings = dict(precomputation_seconds=preparation+preparation_detail["forecast_scenario_seconds"],
                   historical_preparation_seconds=preparation,**preparation_detail,first_seven_days_seconds=first_seven,
                   engine_runtime_seconds=perf_counter()-tick,history_replayed_days=cache.replayed_days)
    return outputs, timings


def validate_annual(outputs):
    """从已执行CSV结构独立复核，不把求解器报告optimal当作唯一验收依据。"""
    actual, daily, plans, scenarios = [outputs[k] for k in
                                     ("actual_schedule","daily_metrics","plan_updates","scenarios_summary")]
    expected_dates = [str(d) for d in FORMAL_DATES]
    if daily.date.tolist()!=expected_dates or len(actual)!=48096:
        raise ValueError("Q3正式年度必须334天及48096个执行时段")
    if actual.duplicated(["date","slot"]).any():
        raise ValueError("Q3年度实际date/slot重复")
    for key, frame in outputs.items():
        if frame.isna().any().any():
            raise ValueError(f"Q3年度{key}含意外缺失")
        numbers = frame.select_dtypes(include=[np.number]).to_numpy(float)
        if not np.isfinite(numbers).all():
            raise ValueError(f"Q3年度{key}含非有限数值")
    if not daily.run_label.eq(ANNUAL_LABEL).all() or not actual.run_label.eq(ANNUAL_LABEL).all():
        raise ValueError("Q3年度参考标签错误")
    for stage in ("primary","secondary","tertiary"):
        if not actual[f"rolling_{stage}_status"].eq("optimal").all():
            raise ValueError("Q3实际三级优化未全部optimal")
    for stage in ("primary","secondary"):
        if not plans[f"{stage}_status"].eq("optimal").all():
            raise ValueError("Q3计划两级优化未全部optimal")
    maximum = float(daily.max_constraint_violation.max())
    cross_day = 0.
    previous_soc = 6000.
    for index, row in daily.iterrows():
        frame = actual[actual.date.eq(row.date)]
        if frame.slot.tolist()!=list(range(1,145)):
            raise ValueError("Q3每日执行slot不完整或未按序排列")
        cross_day = max(cross_day,abs(row.soc_start_kwh-previous_soc))
        checked = validate_schedule(frame,"actual",row.soc_start_kwh)
        maximum = max(maximum,checked["max_violation"],float(frame.rolling_max_violation.max()),
                      abs(row.soc_end_kwh-float(frame.soc_real_end_kwh.iloc[-1])),
                      abs(row.actual_emergency_cost_yuan-checked["cost"]))
        previous_soc = row.soc_end_kwh
        day_plans = plans[plans.date.eq(row.date)]
        price = frame.price_yuan_per_kwh.to_numpy(float)
        initial = day_plans[day_plans.update_time.eq("00:00")]
        if initial.slot.tolist()!=list(range(1,145)):
            raise ValueError("Q3初始计划slot不完整")
        plan_cost = float(price@initial.new_plan_kwh.to_numpy(float))
        adjustments = 0.
        for hour in (0,6,12,18):
            group = scenarios[scenarios.date.eq(row.date)&scenarios.update_time.eq(f"{hour:02d}:00")]
            expected_count = min(14,index+2)
            if (len(group)!=expected_count or row[f"scenario_count_{hour:02d}"]!=expected_count
                    or group.history_date.duplicated().any() or (group.history_date>=row.date).any()):
                raise ValueError("Q3场景日期或早期场景数量不符")
            wanted_history = [str(d.date()) for d in pd.date_range(end=pd.Timestamp(row.date)-pd.Timedelta(days=1),periods=expected_count)]
            if group.history_date.tolist()!=wanted_history:
                raise ValueError("Q3场景未保持最近合法历史日期")
            maximum = max(maximum,float(np.max(np.abs(group.probability.to_numpy(float)-1/expected_count))))
            plan = day_plans[day_plans.update_time.eq(f"{hour:02d}:00")]
            start = hour*6+1
            if plan.slot.tolist()!=list(range(start,145)):
                raise ValueError("Q3滚动计划包含已执行或缺失时段")
            target = float(group.probability.to_numpy(float)@group.terminal_soc_kwh.to_numpy(float))
            executed = frame[frame.slot.between(start,start+35)]
            maximum = max(maximum,float(np.max(np.abs(plan.plan_terminal_soc_kwh-target))),
                          float(np.max(np.abs(executed.plan_terminal_soc_kwh-target))),
                          float(np.max(np.abs(executed.effective_contract_kwh.to_numpy()-plan.new_plan_kwh.iloc[:36].to_numpy()))),
                          abs(float(plan.initial_soc_kwh.iloc[0])-float(executed.soc_real_start_kwh.iloc[0])))
            if hour:
                prior = day_plans[day_plans.update_time.eq(f"{hour-6:02d}:00")&(day_plans.slot>=start)]
                maximum = max(maximum,float(np.max(np.abs(plan.previous_plan_kwh.to_numpy()-prior.new_plan_kwh.to_numpy()))),
                              float(np.max(np.abs(plan.new_plan_kwh-plan.previous_plan_kwh-plan.increase_kwh+plan.decrease_kwh))))
                adjustment = float(price[start-1:]@(1.5*plan.increase_kwh.to_numpy()-.5*plan.decrease_kwh.to_numpy()))
                maximum = max(maximum,abs(adjustment-row[f"adjustment_cost_{hour:02d}_yuan"]))
                adjustments += adjustment
        maximum = max(maximum,abs(plan_cost-row.plan_cost_00_yuan),
                      abs(adjustments-row.adjustment_cost_total_yuan),
                      abs(plan_cost+adjustments+checked["cost"]-row.total_actual_cost_yuan))
        if int((frame.emergency_purchase_kwh>VALIDATION_TOL).sum())!=row.emergency_slot_count:
            raise ValueError("Q3有效紧急购电时段计数不符")
    maximum = max(maximum,cross_day)
    if maximum>VALIDATION_TOL:
        raise RuntimeError(f"Q3年度独立复核最大误差{maximum}超过{VALIDATION_TOL}")
    return dict(max_constraint_violation=maximum,cross_day_soc_max_difference=cross_day)
