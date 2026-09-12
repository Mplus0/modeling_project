"""正式轨迹上的1002次预测经济信息价值诊断，不重新生成实际SOC轨迹。"""
import argparse
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from src.analysis.q3_information_value import run

if __name__=="__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit",type=int,help="仅测试前N条，另存smoke目录")
    args = parser.parse_args()
    run(ROOT,args.limit)
