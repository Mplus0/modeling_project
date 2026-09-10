"""从项目根目录运行：python scripts/01_check_data.py。"""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.common.data_loader import discover_workbooks, file_hash, load_sheets
from src.common.data_validator import validate_sheet


def main():
    parser = argparse.ArgumentParser(description="官方附件只读质量审计")
    parser.add_argument("--raw-dir", type=Path, default=PROJECT_ROOT / "data/raw")
    args = parser.parse_args()
    output = PROJECT_ROOT / "outputs/data_quality"
    raw = args.raw_dir.resolve()
    # 报告只能写入独立目录，且拒绝输出路径通过链接指向原始数据。
    resolved_output = output.resolve()
    if resolved_output == raw or raw in resolved_output.parents:
        raise ValueError("报告目录不可位于原始数据目录中")
    paths = discover_workbooks(raw)
    before = {str(p.relative_to(raw)): file_hash(p) for p in paths}
    report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "inspection_only": True,
        "method": "第一行为表头；保留工作表已声明范围内的空行/空列；缺失含 None、NaN、空字符串及纯空白字符串；原值不变。dtype 为内存推断，原类型另列。数值统计仅含原生数值，min/max/mean 排除非有限值。",
        "workbooks": [], "errors": [],
    }
    for path in paths:
        relative = str(path.relative_to(raw))
        book = {"file": relative, "sha256_before": before[relative], "sheets": []}
        try:
            for sheet in load_sheets(path):
                try:
                    book["sheets"].append(validate_sheet(sheet, "附件5" in path.relative_to(raw).parts))
                except Exception as exc:
                    report["errors"].append({"file": relative, "sheet": sheet["sheet"], "error": str(exc)})
        except Exception as exc:
            report["errors"].append({"file": relative, "error": str(exc)})
        book["sha256_after"] = file_hash(path)
        book["source_unchanged"] = book["sha256_after"] == book["sha256_before"]
        report["workbooks"].append(book)
        print(f"已检查 {relative}: {len(book['sheets'])} 个工作表")
    report["all_sources_unchanged"] = all(b["source_unchanged"] for b in report["workbooks"])
    output.mkdir(parents=True, exist_ok=True)
    # 防止已有报告文件是指向原始附件的符号链接。
    for name in ("audit.json", "summary.md"):
        target = output / name
        if target.is_symlink() or target.resolve().parent != resolved_output:
            raise ValueError(f"报告目标路径不安全: {target}")
    (output / "audit.json").write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    lines = ["# 官方附件只读审计", "", f"原始文件 SHA-256 前后完全一致：{report['all_sources_unchanged']}", "",
             report["method"], "", "完整列统计、缺失位置、时间轴、逐日数量及预报结构见 audit.json。", "",
             "| 文件 | 工作表 | Excel 行×列（含表头） | 数据行 | 缺失单元格 | 重复行（额外） |", "|---|---|---|---:|---:|---:|"]
    for book in report["workbooks"]:
        for sheet in book["sheets"]:
            lines.append(f"| {book['file']} | {sheet['sheet']} | {sheet['excel_rows']}×{sheet['excel_columns']} | {sheet['data_rows']} | {sheet['missing_cells']} | {sheet['duplicated_rows_extra']} |")
    lines.extend(["", "## 时间轴与待确认事项", ""])
    for book in report["workbooks"]:
        for sheet in book["sheets"]:
            lines.extend([f"### {book['file']} / {sheet['sheet']}", ""])
            for name, axis in sheet["time"]["axes"].items():
                lines.append(f"- {name}：解析 {axis['resolved_records']}/{axis['total_records']}，额外重复 {axis['duplicate_extra_count']}，参考间隔 {axis['reference_step_seconds']} 秒，间隔一致 {axis['interval_consistent']}，可解析首尾内缺失 {axis['missing_timestamp_count']}。")
            lines.extend(f"- {note}" for note in sheet["notes"] + sheet["time"]["notes"])
            lines.append("")
    if report["errors"]:
        lines.extend(["## 审计错误（报告不完整）", "", json.dumps(report["errors"], ensure_ascii=False, indent=2)])
    (output / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"报告已保存: {output}")
    return 1 if report["errors"] or not report["all_sources_unchanged"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
