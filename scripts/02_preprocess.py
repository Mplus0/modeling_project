"""运行标准化预处理。"""

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.common.preprocessing import run_preprocessing


def main():
    try:
        outputs, filled_rows = run_preprocessing(
            PROJECT_ROOT / "data/raw", PROJECT_ROOT / "data/processed",
            PROJECT_ROOT / "outputs/data_quality/preprocessing_summary.md",
        )
    except (ValueError, OSError) as exc:
        print(f"预处理停止：{exc}", file=sys.stderr)
        return 1
    for name, frame in outputs.items():
        print(f"data/processed/{name}: {len(frame)} 行")
    print(f"附件 3：结构验证通过后推导 {len(filled_rows)} 个空白日期；原始文件哈希未变。")
    print("报告：outputs/data_quality/preprocessing_summary.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
