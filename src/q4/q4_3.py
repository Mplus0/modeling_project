"""通过价格数组适配器直接运行冻结Q3完整日循环，之后另行真实结算。"""

import numpy as np
import pandas as pd
from src.q3.simulation import simulate_day
from src.q4.price_forecasting import PriceStream

REFERENCE_LABEL = "Q4-3 PROVISIONAL / PAPER REFERENCE ONLY; NOT FINAL Q4-3 PARAMETER"


def run_day(day, observe, midnight_pv_kw, load, baseline, issues, records, residuals,
            start_soc, alpha, risk_weight, label, stream_factory=PriceStream):
    stream = stream_factory(baseline)
    def reveal(slot):
        current_load,current_pv,current_price = observe(slot)
        stream.reveal(slot,current_price)
        return current_load,current_pv
    # 原循环在观测回调之前更新合同，因此合同只看上一slot及更早的价格。
    result = simulate_day(day,reveal,midnight_pv_kw,load,stream,issues,records,residuals,
                          start_soc,alpha,risk_weight,run_label=label)
    actual,plans,daily = [result[k] for k in ("actual_schedule","plan_updates","daily_metrics")]
    real = np.asarray(stream.observed)
    refresh = pd.DataFrame(stream.refreshes)
    refresh.insert(0,"date",str(day))
    refresh["baseline_price_yuan_per_kwh"] = baseline
    result["price_refresh"] = refresh
    plans["predicted_adjustment_cost_yuan"] = plans.adjustment_cost_yuan
    for hour in (0,6,12,18):
        mask = plans.update_time.eq(f"{hour:02d}:00")
        indices = plans.loc[mask,"slot"].to_numpy(int)-1
        gamma = 1. if hour==0 else float(refresh.gamma.iloc[hour*6-1])
        plans.loc[mask,"price_forecast_yuan_per_kwh"] = gamma*np.asarray(baseline)[indices]
        plans.loc[mask,"contract_gamma"] = gamma
        plans.loc[mask,"price_real_yuan_per_kwh"] = real[indices]
        plans.loc[mask,"adjustment_cost_yuan"] = real[indices]*(1.5*plans.loc[mask,"increase_kwh"]-.5*plans.loc[mask,"decrease_kwh"])
        key = "plan_cost_00_yuan" if hour==0 else f"adjustment_cost_{hour:02d}_yuan"
        daily[f"predicted_{key}"] = daily[key]
        daily[key] = (float(real@plans.loc[mask,"new_plan_kwh"]) if hour==0
                      else float(plans.loc[mask,"adjustment_cost_yuan"].sum()))
    # Q3实际首行价格已是真实值；初始合同及每轮u/v在执行完以后统一用真实价格结算。
    initial = plans[plans.update_time.eq("00:00")].new_plan_kwh.to_numpy()
    net_fee = plans.groupby("slot").adjustment_cost_yuan.sum().reindex(range(1,145)).to_numpy()
    actual["initial_plan_cost_real_yuan"] = real*initial
    actual["adjustment_cost_real_yuan"] = net_fee
    actual["settled_total_cost_yuan"] = real*initial+net_fee+actual.emergency_cost_slot_yuan
    daily["adjustment_cost_total_yuan"] = sum(daily[f"adjustment_cost_{h:02d}_yuan"] for h in (6,12,18))
    daily["total_actual_cost_yuan"] = daily.plan_cost_00_yuan+daily.adjustment_cost_total_yuan+daily.actual_emergency_cost_yuan
    return result
