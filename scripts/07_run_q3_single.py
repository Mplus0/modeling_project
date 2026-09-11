"""仅执行Q3连续1至3日参考验证，不生成正式提交或参数搜索。"""

import argparse
import json
from datetime import date
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

from src.common.data_loader import file_hash
from src.q2.forecasting import load_daily_inputs
from src.q3.forecast import load_hourly_forecasts
from src.q3.simulation import simulate_days
from src.q3.metrics import write_outputs


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start-date",type=date.fromisoformat,default=date(2025,3,20))
    parser.add_argument("--days",type=int,choices=(1,2,3),default=1)
    parser.add_argument("--alpha",type=float,choices=(.90,.95,.99),required=True)
    parser.add_argument("--lambda",dest="risk_weight",type=float,choices=(0,.25,.5,1,2),required=True)
    parser.add_argument("--initial-soc",type=float,default=6000)
    parser.add_argument("--output-dir",type=Path,default=Path("outputs/q3/single"))
    args = parser.parse_args()
    output = (ROOT/args.output_dir).resolve()
    if not output.is_relative_to((ROOT/"outputs/q3").resolve()):
        parser.error("参考结果只能写入outputs/q3/，不能覆盖其他问题或正式提交")
    if args.start_date != date(2025,3,20) or args.initial_soc != 6000:
        parser.error("当前人工初始化仅获准用于2025-03-20起始的6000kWh参考测试")
    # 读取前后逐文件检查原始、预处理及已有Q1/Q2结果，禁止静默覆盖冻结阶段。
    protected = [p for folder in (ROOT/"data",ROOT/"src/common",ROOT/"src/q1",ROOT/"src/q2",ROOT/"outputs")
                 for p in folder.rglob("*") if p.is_file() and "__pycache__" not in p.parts
                 and not p.is_relative_to(ROOT/"outputs/q3")]
    before = {str(p.relative_to(ROOT)):file_hash(p) for p in protected}
    print("TEST / REFERENCE ONLY：开始Q3单组参考验证",flush=True)
    failure = None
    try:
        history,price = load_daily_inputs(ROOT/"data/processed/historical_power.csv",ROOT/"data/processed/q1_input.csv")
        issues = load_hourly_forecasts(ROOT/"data/processed/pv_forecast_hourly.csv")
        outputs = simulate_days(history,issues,price,args.start_date,args.days,args.initial_soc,args.alpha,args.risk_weight)
    except ValueError as exc:
        failure = exc
    finally:
        after = {str(p.relative_to(ROOT)):file_hash(p) for p in protected}
        if before != after:
            raise RuntimeError("Q3参考运行发现受保护文件SHA-256变化")
    if failure is not None:
        output.mkdir(parents=True,exist_ok=True)
        diagnostic = dict(run_label="TEST / REFERENCE ONLY",completed=False,error=str(failure),
                          sha256_unchanged=True,files_checked=len(before),sha256=before)
        (output/"q3_validation_failure.json").write_text(json.dumps(diagnostic,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
        raise failure
    metrics = write_outputs(outputs,output,dict(sha256_unchanged=True,files_checked=len(before),sha256=before))
    # 本次完整通过后清理同目录旧失败标记，避免误认为当前运行仍被阻塞。
    (output/"q3_validation_failure.json").unlink(missing_ok=True)
    print(json.dumps({k:v for k,v in metrics.items() if k != "integrity"},ensure_ascii=False,indent=2))


if __name__ == "__main__":
    main()
