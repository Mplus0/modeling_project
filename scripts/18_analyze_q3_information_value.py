"""显示已验证的Q3 Vdk诊断；不会启动优化。"""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.analysis.q3_information_value import load_validated


if __name__ == "__main__":
    print(load_validated(ROOT))
