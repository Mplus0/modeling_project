"""仅读取已完成的 Q1 输入和结果，生成五组论文图片。"""

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.q1.plotting import plot_q1


def main():
    paths = plot_q1(PROJECT_ROOT / "data/processed/q1_input.csv",
                    PROJECT_ROOT / "outputs/schedule/q1_schedule.csv",
                    PROJECT_ROOT / "outputs/metrics/q1_metrics.json",
                    PROJECT_ROOT / "outputs/figures/q1")
    print("绘图校验通过；Q1 输入及数值结果哈希未变。已生成：")
    for path in paths:
        print(path.relative_to(PROJECT_ROOT))
    print("论文图片索引：outputs/figures/q1/README.md")


if __name__ == "__main__":
    main()
