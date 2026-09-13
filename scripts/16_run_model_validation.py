"""独立模型检验入口；不运行参数搜索或正式结果写入。"""

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.analysis.model_validation import accept_reference, branch_check, run_experiment, summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("accept", "q2", "q3", "q4", "summary"))
    parser.add_argument("--smoke", action="store_true", help="仅首日轻量验证，输出独立smoke目录")
    args = parser.parse_args()
    print(branch_check(ROOT), flush=True)
    try:
        if args.stage == "accept":
            print(accept_reference(ROOT), flush=True)
        elif args.stage in ("q2", "q3"):
            print(run_experiment(ROOT, args.stage, args.smoke), flush=True)
        elif args.stage == "q4":
            from src.analysis.q4_price_blind import run_experiment as run_q4
            print(run_q4(ROOT, args.smoke), flush=True)
    finally:
        summary(ROOT)
