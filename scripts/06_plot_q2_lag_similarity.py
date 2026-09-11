"""Q2历史日曲线相似性绘图入口，仅写本任务的CSV、PNG和PDF。"""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.common.data_loader import file_hash
from src.q2.lag_similarity import build_daily_matrix, compute_lag_similarity, load_and_validate_historical_power, plot_lag_similarity


def main(root=ROOT):
    root = Path(root)
    source = root / "data/processed/historical_power.csv"
    before = file_hash(source)
    table = compute_lag_similarity(*build_daily_matrix(load_and_validate_historical_power(source)))
    destination = root / "outputs/metrics/q2/q2_lag_similarity.csv"
    destination.parent.mkdir(parents=True, exist_ok=True)
    table.to_csv(destination, index=False, encoding="utf-8")
    folder = root / "outputs/figures/q2"
    plot_lag_similarity(table, folder)
    if file_hash(source) != before:
        raise RuntimeError("冻结历史数据SHA-256发生变化")
    print(f"已生成14行滞后指标：{destination}\n图片：{folder / 'q2_lag_similarity.png'}\n矢量版：{folder / 'q2_lag_similarity.pdf'}\n输入SHA-256未变。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
