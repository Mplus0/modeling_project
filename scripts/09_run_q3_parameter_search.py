"""Q3二十组串行全年实验；按组验证恢复，所有组通过后统一评分。"""

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

from src.common.data_loader import file_hash
from src.q2.forecasting import load_daily_inputs
from src.q3.forecast import load_hourly_forecasts
from src.q3.search_runner import run_search, validate_reference


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workers",type=int,choices=(1,),default=1,help="本阶段只支持串行，各组状态完全独立")
    parser.add_argument("--validate-only",action="store_true",help="仅验证已有完整reference，不启动实验")
    args = parser.parse_args()
    search = (ROOT/"outputs/q3/search").resolve()
    if search != ROOT.resolve()/"outputs/q3/search":
        parser.error("搜索目录不能链接到其他输出位置")
    protected = [p for folder in (ROOT/"data",ROOT/"src/common",ROOT/"src/q1",ROOT/"src/q2",ROOT/"outputs")
                 for p in folder.rglob("*") if p.is_file() and "__pycache__" not in p.parts and not p.is_relative_to(search)]
    before = {str(p.relative_to(ROOT)):file_hash(p) for p in protected}
    model_files = [ROOT/f"src/q3/{name}.py" for name in ("annual","forecast","confidence","scenarios","optimizer","simulation","parameters")]
    fingerprint = {str(p.relative_to(ROOT)):file_hash(p) for p in model_files}
    fingerprint.update({k:v for k,v in before.items() if k.startswith(("data", "src"))})
    signature = hashlib.sha256(json.dumps(fingerprint,sort_keys=True).encode()).hexdigest()
    def integrity():
        if any(file_hash(ROOT/p)!=h for p,h in before.items()):
            raise RuntimeError("Q3搜索保护文件SHA-256发生变化")
        return dict(sha256_unchanged=True,files_checked=len(before),sha256=before)
    try:
        if args.validate_only:
            _,metrics = validate_reference(ROOT/"outputs/q3/annual/reference_a0.90_l0.50")
            print(f"reference验证通过: days={metrics['days']} slots={metrics['slots']} cost={metrics['total_actual_cost_yuan']}")
            return
        history,price = load_daily_inputs(ROOT/"data/processed/historical_power.csv",ROOT/"data/processed/q1_input.csv")
        issues = load_hourly_forecasts(ROOT/"data/processed/pv_forecast_hourly.csv")
        summary = run_search(ROOT,history,issues,price,signature,integrity)
        print(json.dumps({k:v for k,v in summary.items() if k not in ("integrity","groups")},ensure_ascii=False,indent=2))
    finally:
        integrity()


if __name__=="__main__":
    main()
