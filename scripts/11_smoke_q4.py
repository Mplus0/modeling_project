"""Q4 smoke入口，参数及运行范围由src/q4/cli.py统一约束。"""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from src.q4.cli import main

if __name__=="__main__":
    main("smoke",ROOT)
