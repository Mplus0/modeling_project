"""先发布完整调度与指标并复核，再按明确时间映射填写官方模板。"""

import argparse
import json
from pathlib import Path
import sys

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.common.data_loader import discover_workbooks, file_hash
from src.q1.optimizer import INPUT_COLUMNS, evaluate_schedule, load_input, solve_q1
from src.q1.result_writer import write_result


def main():
    parser = argparse.ArgumentParser(description="Q1 连续线性规划与词典序二级优化")
    parser.add_argument("--interval-map", type=Path, help="经建模手确认的 JSON：按 slot 顺序排列的 144 个模板区间标签")
    args = parser.parse_args()
    frozen = discover_workbooks(PROJECT_ROOT / "data/raw") + sorted((PROJECT_ROOT / "data/processed").glob("*.csv"))
    before = {p: file_hash(p) for p in frozen}
    schedule, metrics = solve_q1(load_input(PROJECT_ROOT / "data/processed/q1_input.csv"))
    metrics["input_sha256"] = before[PROJECT_ROOT / "data/processed/q1_input.csv"]
    metrics["frozen_data_unchanged"] = all(file_hash(p) == h for p, h in before.items())
    metrics["submission_status"] = "pending_validation"
    metrics["remaining_todos"] = []
    schedule_path = PROJECT_ROOT / "outputs/schedule/q1_schedule.csv"
    metrics_path = PROJECT_ROOT / "outputs/metrics/q1_metrics.json"
    for path in (schedule_path, metrics_path):
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.is_symlink() or (PROJECT_ROOT / "data").resolve() in path.resolve().parents:
            raise ValueError("输出路径不能指向冻结数据")
    # 无论验证成功与否，先保留完整变量和残差；失败时禁止继续生成 Excel。
    schedule.to_csv(schedule_path, index=False, encoding="utf-8")
    metrics_path.write_text(json.dumps(metrics, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps(metrics, ensure_ascii=False, indent=2, allow_nan=False), flush=True)
    saved = pd.read_csv(schedule_path, float_precision="round_trip", keep_default_na=False)
    checked = evaluate_schedule(saved, metrics["C_star"], metrics["secondary_solver_objective"])
    if not saved[INPUT_COLUMNS].equals(schedule[INPUT_COLUMNS]):
        raise RuntimeError("CSV 输入列往返不一致")
    if not checked["validation_passed"] or not metrics["validation_passed"] or not metrics["frozen_data_unchanged"]:
        raise RuntimeError("调度独立复核或冻结数据完整性检查失败；未生成 Excel")
    mapping = json.loads(args.interval_map.read_text(encoding="utf-8")) if args.interval_map else None
    if mapping is not None and (not isinstance(mapping, list) or not all(isinstance(label, str) for label in mapping)):
        raise ValueError("时间映射 JSON 必须是区间标签字符串列表")
    destination = write_result(saved, metrics, PROJECT_ROOT / "data/raw/附件5/result1.xlsx",
                               PROJECT_ROOT / "outputs/submissions/result1.xlsx", mapping)
    if not all(file_hash(p) == h for p, h in before.items()):
        raise RuntimeError("冻结数据哈希检查失败")
    metrics.update(submission_status="written", remaining_todos=[],
                   interval_mapping=mapping if mapping is not None else "slot i -> template row i+1; original labels unchanged")
    metrics_path.write_text(json.dumps(metrics, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(f"结果已写入：{destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
