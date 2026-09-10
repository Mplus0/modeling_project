"""统计原始单元格质量，仅返回审计结果。"""

from collections import Counter
from numbers import Real
import math

from src.common.time_utils import TODO, inspect_times, is_blank


def validate_sheet(sheet, is_template=False):
    frame, headers = sheet["frame"], sheet["headers"]
    columns = []
    for i, header in enumerate(headers):
        values = frame.iloc[:, i]
        blank = [is_blank(v) for v in values]
        # 不强制转换文本数字；混合列仅统计原本就是数值的单元格。
        numeric = [v for v in values if isinstance(v, Real) and not isinstance(v, bool) and not is_blank(v)]
        finite = [float(v) for v in numeric if math.isfinite(v)]
        columns.append({
            "excel_column": i + 1, "name": str(header) if header is not None else None,
            "header_type": type(header).__name__,
            "dtype": str(values.infer_objects().dtype),
            "raw_type_counts": dict(Counter(type(v).__name__ for v in values)),
            "missing_count": sum(blank),
            "missing_excel_rows": [r + 2 for r, missing in enumerate(blank) if missing],
            "numeric_count": len(numeric), "nonfinite_count": len(numeric) - len(finite),
            "numeric_min": min(finite) if finite else None,
            "numeric_max": max(finite) if finite else None,
            "numeric_mean": sum(finite) / len(finite) if finite else None,
            "negative_count": sum(v < 0 for v in numeric),
            "zero_count": sum(v == 0 for v in numeric),
            "formula_count": sum(isinstance(v, str) and v.startswith("=") for v in values),
        })
    duplicated = frame.duplicated(keep=False)
    result = {k: v for k, v in sheet.items() if k not in {"frame", "headers"}}
    result.update({
        "is_official_template": is_template,
        "data_rows": len(frame), "data_columns": len(headers),
        "header_excel_row": 1, "columns": columns,
        "duplicate_header_names": [str(h) for h, n in Counter(headers).items() if n > 1],
        "missing_cells": sum(c["missing_count"] for c in columns),
        "duplicated_rows_extra": int(frame.duplicated().sum()),
        "duplicated_rows_all_excel_rows": [i + 2 for i, flag in enumerate(duplicated) if flag],
        "time": inspect_times(frame, headers),
        "notes": [f"{TODO}：缺失、重复、负值和零值的业务含义及是否处理；本阶段仅统计。"],
    })
    if is_template:
        result["notes"].append("官方结果模板的空白也计入统计，不作为观测数据异常自动处理。")
    if any(c["formula_count"] for c in columns):
        result["notes"].append(f"{TODO}：公式未求值，数值统计不包含公式计算结果。")
    return result
