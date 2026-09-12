"""Q4独立逐日运行入口：每次创建独立缓存与6000kWh初态。"""

from datetime import timedelta
from time import perf_counter
import pandas as pd
from src.q3.annual import FORMAL_DATES, HistoricalCache
from src.q3.parameters import PARAMETER_GRID
from src.q4.q4_2 import ForecastCache, run_day as run_two
from src.q4.q4_3 import run_day as run_three
from src.q4.price_forecasting import forecast_price
from src.q4.validation import validate_outputs


def run_dates(history, prices, issues, variant, dates, label, alpha=.85, risk_weight=.25, progress=None):
    dates = tuple(dates)
    if variant not in (2,3) or not dates or dates!=tuple(pd.date_range(dates[0],dates[-1]).date):
        raise ValueError("Q4类型或连续日期不合法")
    if any(d not in FORMAL_DATES for d in dates) or (alpha,risk_weight) not in PARAMETER_GRID:
        raise ValueError("Q4日期或参数不在确认范围")
    cache = ForecastCache(history) if variant==2 else HistoricalCache(history,issues)
    price_cache,results,soc = {},[],6000.
    tick = perf_counter()
    for count,day in enumerate(dates,1):
        baseline,price_diagnostic = forecast_price({d:p for d,p in prices.items() if d<day},day,price_cache)
        # 未来真实数据只封装在单项观测回调中；求解器只接收当前三个标量。
        observation = history[day]
        def observe(slot):
            return float(observation["load"][slot-1]),float(observation["pv"][slot-1]),float(prices[day][slot-1])
        if variant==2:
            forecast,risk,diagnostic = cache.prepare(day)
            result = run_two(day,observe,forecast,risk,baseline,soc,label)
            result["forecast_selection"] = pd.DataFrame([diagnostic])
        else:
            load,records,residuals = cache.prepare(day)
            result = run_three(day,observe,float(history[day-timedelta(days=1)]["pv"][-1])*6,
                               load,baseline,issues,records,residuals,soc,alpha,risk_weight,label)
        result["actual_schedule"]["source_time"] = observation["source_time"]
        result["price_selection"] = pd.DataFrame([price_diagnostic])
        soc = float(result["daily_metrics"].soc_end_kwh.iloc[0])
        results.append(result)
        if progress and (count%10==0 or count==len(dates)):
            progress(count,len(dates),day)
    outputs = {k:pd.concat([r[k] for r in results],ignore_index=True) for k in results[0]}
    validate_outputs(outputs,variant,formal=dates==FORMAL_DATES)
    return outputs,perf_counter()-tick
