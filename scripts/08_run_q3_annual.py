"""Q3单组正式334天年度参考，先通过旧三日结果等价门槛。"""

import argparse
import json
import sys
from pathlib import Path
from datetime import date
from time import perf_counter

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

from src.common.data_loader import file_hash
from src.q2.forecasting import load_daily_inputs
from src.q3.forecast import load_hourly_forecasts
from src.q3.annual import run_dates, FORMAL_DATES
from src.q3.metrics import write_annual_outputs
from src.q3.optimizer import VALIDATION_TOL
from src.q3.parameters import ALPHA_CHOICES, LAMBDA_CHOICES


def compare_reference(outputs, reference):
    differences = {}
    for key,frame in outputs.items():
        old = pd.read_csv(reference/f"q3_{key}.csv",float_precision="round_trip")
        if len(frame)!=len(old) or not set(old.columns).issubset(frame.columns):
            raise RuntimeError(f"Q3年度三日回归{key}结构不一致")
        maximum = 0.
        for col in old:
            if col == "run_label":
                continue
            if pd.api.types.is_numeric_dtype(old[col]):
                maximum = max(maximum,float(np.max(np.abs(frame[col].to_numpy(float)-old[col].to_numpy(float)))))
            elif frame[col].astype(str).tolist()!=old[col].astype(str).tolist():
                raise RuntimeError(f"Q3年度三日回归{key}/{col}不一致")
        if maximum>VALIDATION_TOL:
            raise RuntimeError(f"Q3年度三日回归{key}最大差异{maximum}超过容差")
        differences[key] = maximum
    return differences


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--alpha",type=float,choices=ALPHA_CHOICES,required=True)
    parser.add_argument("--lambda",dest="risk_weight",type=float,choices=LAMBDA_CHOICES,required=True)
    parser.add_argument("--regression-only",action="store_true")
    args = parser.parse_args()
    output = ROOT/f"outputs/q3/annual/reference_a{args.alpha:.2f}_l{args.risk_weight:.2f}"
    protected = [p for folder in (ROOT/"data",ROOT/"src/common",ROOT/"src/q1",ROOT/"src/q2",ROOT/"outputs")
                 for p in folder.rglob("*") if p.is_file() and "__pycache__" not in p.parts
                 and not p.is_relative_to(ROOT/"outputs/q3/annual")]
    before = {str(p.relative_to(ROOT)):file_hash(p) for p in protected}
    try:
        load_tick = perf_counter()
        history,price = load_daily_inputs(ROOT/"data/processed/historical_power.csv",ROOT/"data/processed/q1_input.csv")
        issues = load_hourly_forecasts(ROOT/"data/processed/pv_forecast_hourly.csv")
        loading_seconds = perf_counter()-load_tick
        reference = ROOT/"outputs/q3/single"
        prior_metrics = json.loads((reference/"q3_single_metrics.json").read_text(encoding="utf-8"))
        print("验证年度缓存与原三日参考结果的一致性……",flush=True)
        regression, _ = run_dates(history,issues,price,tuple(pd.date_range("2025-03-20","2025-03-22").date),
                                   6000.,prior_metrics["alpha"],prior_metrics["lambda"])
        differences = compare_reference(regression,reference)
        regression_dir = ROOT/"outputs/q3/annual/regression"
        regression_dir.mkdir(parents=True,exist_ok=True)
        (regression_dir/"q3_engine_equivalence.json").write_text(json.dumps(dict(passed=True,tolerance=VALIDATION_TOL,
                                                                                maximum_differences=differences),ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
        print(f"三日回归通过，最大数值差异 {max(differences.values()):.3g}",flush=True)
        if args.regression_only:
            return
        started = perf_counter()
        progress = lambda count,total,day: print(f"Q3 annual reference completed {count}/{total} days: {day}",flush=True)
        outputs,timings = run_dates(history,issues,price,FORMAL_DATES,6000.,args.alpha,args.risk_weight,progress)
        timings.update(runtime_seconds=perf_counter()-started+loading_seconds,loading_seconds=loading_seconds,
                       preparation_scope="输入加载另计；precomputation_seconds含历史/负荷准备及按发布时刻构造的光伏与场景")
        after = {str(p.relative_to(ROOT)):file_hash(p) for p in protected}
        if before!=after:
            raise RuntimeError("Q3年度运行冻结文件SHA-256变化")
        metrics = write_annual_outputs(outputs,output,timings,dict(sha256_unchanged=True,files_checked=len(before),sha256=before))
        print(json.dumps({k:v for k,v in metrics.items() if k!="integrity"},ensure_ascii=False,indent=2),flush=True)
    finally:
        if any(file_hash(ROOT/p)!=h for p,h in before.items()):
            raise RuntimeError("Q3年度入口运行前后冻结文件SHA-256不一致")


if __name__=="__main__":
    main()
