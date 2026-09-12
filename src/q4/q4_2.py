"""Q2预测及风险完全复用，仅把逐步价格预测传给原三级滚动求解器。"""

from datetime import timedelta
import numpy as np
import pandas as pd
from src.q2.forecasting import forecast_day, M_LOAD, K_PV
from src.q2.risk import historical_risk
from src.q2.optimizer import solve_plan, validate_schedule, ETA_CHARGE, ETA_DISCHARGE
from src.q2.rolling import solve_actual_rolling_step
from src.q4.price_forecasting import PriceStream


class ForecastCache:
    def __init__(self, history):
        self.history = history
        self.prior,self.residuals,self.cache = {},{},{}
        self.dates = sorted(history)
        self.cursor = 0
        self.first = min(history)+timedelta(days=max(max(M_LOAD)*7,max(K_PV))+1)

    def prepare(self, day):
        while self.cursor<len(self.dates) and self.dates[self.cursor]<day:
            past = self.dates[self.cursor]
            if past>=self.first:
                prediction,_ = forecast_day(self.prior,past,self.cache)
                observed = self.history[past]
                self.residuals[past] = observed["load"]-observed["pv"]-(prediction["load"]-prediction["pv"])
            self.prior[past] = self.history[past]
            self.cursor += 1
        forecast,diagnostic = forecast_day(self.prior,day,self.cache)
        risk,dates = historical_risk(self.residuals,day)
        diagnostic.update(residual_dates="|".join(map(str,dates)),historical_error_sample_count=len(dates))
        return forecast,risk,diagnostic


def run_day(day, observe, forecast, risk, baseline, start_soc, label, stream_factory=PriceStream):
    stream = stream_factory(baseline)
    demand = forecast["load"]-forecast["pv"]+risk
    plan,pm = solve_plan(demand,forecast["pv"],baseline,start_soc,day)
    grid = plan.grid_purchase_plan_kwh.to_numpy(copy=True)
    rows,soc = [],float(start_soc)
    for slot in range(1,145):
        load,pv,price = observe(slot)
        stream.reveal(slot,price)
        horizon,checked = solve_actual_rolling_step(slot,load,pv,forecast["load"],forecast["pv"],
                                                   np.asarray(stream),grid,soc,start_soc,day)
        row = horizon.iloc[0].to_dict()
        # 只执行首行，次日及下一步均继承真实递推终态；不重置SOC。
        soc += ETA_CHARGE*(row["x_real_kwh"]+row["q_real_kwh"])-row["z_real_kwh"]/ETA_DISCHARGE
        row.update(soc_real_end_kwh=soc,run_label=label,load_forecast_kwh=forecast["load"][slot-1],
                   pv_forecast_kwh=forecast["pv"][slot-1],rolling_max_violation=checked["max_violation"],
                   rolling_primary_star=checked["primary_star"],rolling_terminal_gap_star=checked["terminal_gap_star"],
                   rolling_tertiary_throughput_star=checked["tertiary_objective"])
        row.update({f"rolling_{s}_status":checked[f"{s}_status"] for s in ("primary","secondary","tertiary")})
        rows.append(row)
    actual = pd.DataFrame(rows)
    check = validate_schedule(actual,"actual",start_soc)
    plan["price_forecast_yuan_per_kwh"] = baseline
    plan["price_real_yuan_per_kwh"] = stream.observed
    plan["settled_plan_cost_yuan"] = np.asarray(stream.observed)*grid
    plan["primary_status"],plan["secondary_status"] = pm["primary_status"],pm["secondary_status"]
    plan["max_constraint_violation"] = pm["max_violation"]
    daily = dict(date=str(day),run_label=label,soc_start_kwh=start_soc,soc_end_kwh=soc,
                 soc_min_kwh=min(start_soc,actual.soc_real_end_kwh.min()),soc_max_kwh=max(start_soc,actual.soc_real_end_kwh.max()),
                 plan_cost_00_yuan=float(actual.planned_cost_slot_yuan.sum()),predicted_plan_cost_00_yuan=pm["cost"],
                 adjustment_cost_total_yuan=0.,actual_emergency_cost_yuan=check["cost"],
                 actual_emergency_purchase_kwh=float(actual.emergency_purchase_kwh.sum()),
                 total_actual_cost_yuan=float(actual.total_cost_slot_yuan.sum()),
                 emergency_slot_count=int((actual.emergency_purchase_kwh>1e-6).sum()),
                 actual_throughput_kwh=check["throughput"],simultaneous_slots=check["simultaneous_slots"],
                 max_constraint_violation=max(check["max_violation"],pm["max_violation"],actual.rolling_max_violation.max()))
    refresh = pd.DataFrame(stream.refreshes)
    refresh.insert(0,"date",str(day))
    refresh["baseline_price_yuan_per_kwh"] = baseline
    return dict(plan_schedule=plan,actual_schedule=actual,daily_metrics=pd.DataFrame([daily]),price_refresh=refresh)
