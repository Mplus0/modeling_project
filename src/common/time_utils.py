"""时间标签的只读解释及时间轴审计，不生成处理后数据。"""

from collections import Counter
from datetime import date, datetime, time
import re

import pandas as pd

TODO = "TODO: 需建模手确认"


def is_blank(value):
    return value is None or (isinstance(value, str) and not value.strip()) or bool(pd.isna(value))


def clock_seconds(value):
    if isinstance(value, time):
        return value.hour * 3600 + value.minute * 60 + value.second
    if not isinstance(value, str):
        return None
    match = re.fullmatch(r"(\d{1,2}):(\d{1,2})(?::(\d{1,2}))?(?:\+(\d+))?", value)
    if not match:
        return None
    hour, minute, second, day = (int(x or 0) for x in match.groups())
    if hour > 24 or minute > 59 or second > 59 or (hour == 24 and (minute or second)):
        return None
    # +1 和 24:00 是原标签显式给出的跨日信息，不按行序猜测午夜。
    return day * 86400 + hour * 3600 + minute * 60 + second


def parse_date(value):
    if isinstance(value, (datetime, date)):
        return pd.Timestamp(value)
    if isinstance(value, str) and re.fullmatch(r"\d{4}[-/]\d{1,2}[-/]\d{1,2}", value):
        try:
            return pd.Timestamp(value)
        except ValueError:
            pass
    return None


def audit_axis(values, step_seconds, absolute=False):
    """按明确声明的参考间隔检查；缺口仅限可解析时间轴的首尾之间。"""
    valid = [v for v in values if v is not None]
    counts = Counter(valid)
    unique = sorted(counts)
    def label(v):
        return pd.Timestamp(v, unit="s").isoformat() if absolute else v
    deltas = [b - a for a, b in zip(valid, valid[1:])]
    # 排序和去重仅用于集合比较；原始顺序、重复项及数据均保留。
    missing = []
    off_grid = []
    if unique:
        off_grid = [label(v) for v in unique if (v - unique[0]) % step_seconds]
        for value in range(int(unique[0]), int(unique[-1]) + 1, step_seconds):
            if value not in counts:
                missing.append(label(value))
    per_day = Counter(pd.Timestamp(v, unit="s").date().isoformat() for v in valid) if absolute else {}
    return {
        "reference_step_seconds": step_seconds,
        "scope": "可解析标签的最小值至最大值；不推断边界外缺失",
        "total_records": len(values), "resolved_records": len(valid),
        "unresolved_records": len(values) - len(valid),
        "start": label(unique[0]) if unique else None,
        "end": label(unique[-1]) if unique else None,
        "duplicate_extra_count": sum(n - 1 for n in counts.values()),
        "duplicates": [{"timestamp": label(v), "count": n} for v, n in sorted(counts.items()) if n > 1],
        "interval_counts_seconds_in_source_order": dict(sorted(Counter(deltas).items())),
        "non_increasing_intervals": sum(d <= 0 for d in deltas),
        "interval_consistent": all(d == step_seconds for d in deltas) if deltas else None,
        "off_grid_timestamps": off_grid,
        "missing_timestamp_count": len(missing), "missing_timestamps": missing,
        "records_per_calendar_day": dict(sorted(per_day.items())),
    }


def epoch(value):
    return int(value.value // 10**9) if value is not None else None


def inspect_times(frame, headers):
    result = {"notes": [], "axes": {}}
    if not headers:
        result["notes"].append("空表，无可审计时间轴")
        return result
    dates = [parse_date(v) for v in frame.iloc[:, 0]]
    if "预报时刻" in headers:
        clock_col = headers.index("预报时刻")
        clocks = [clock_seconds(v) for v in frame.iloc[:, clock_col]]
        # 日期空白绝不前向填充；只能组合同一行显式存在的日期和时刻。
        issues = [epoch(d) + t if d is not None and t is not None else None
                  for d, t in zip(dates, clocks)]
        leads = [(i, int(m.group(1))) for i, h in enumerate(headers)
                 if (m := re.fullmatch(r"预报(\d+)小时", str(h)))]
        result["axes"]["explicit_issue_times"] = audit_axis(issues, 21600, True)
        result["axes"]["candidate_targets_from_explicit_issues"] = audit_axis(
            [v + h * 3600 for v in issues if v is not None for _, h in leads], 3600, True)
        result["forecast"] = {
            "issue_clock_counts": dict(Counter(str(v) for v in frame.iloc[:, clock_col])),
            "lead_hours": [h for _, h in leads],
            "lead_hour_axis": audit_axis([h * 3600 for _, h in leads], 3600),
            "unresolved_issue_excel_rows": [i + 2 for i, v in enumerate(issues) if v is None],
            "target_time_interpretation": "候选标签解释：目标时间 = 显式发布时刻 + 表头小时数；点值/区间含义未确定",
            "targets_by_explicit_issue": [
                {"excel_row": i + 2, "issue_time": pd.Timestamp(v, unit="s").isoformat(),
                 "target_times": [pd.Timestamp(v + h * 3600, unit="s").isoformat() for _, h in leads],
                 "nonblank_forecast_values": sum(not is_blank(frame.iat[i, c]) for c, _ in leads)}
                for i, v in enumerate(issues) if v is not None],
        }
        result["notes"].append(f"{TODO}：空白日期所属发布日、发布频次及预报目标点值/区间语义；未填充日期。缺口仅针对显式可解析发布时刻。")
        return result
    slots = [(i, clock_seconds(h)) for i, h in enumerate(headers) if clock_seconds(h) is not None]
    if slots and any(d is not None for d in dates):
        result["axes"]["header_time_offsets"] = audit_axis([t for _, t in slots], 600)
        result["axes"]["row_dates"] = audit_axis([epoch(d) for d in dates], 86400, True)
        timestamps = [epoch(d) + t if d is not None else None for d in dates for _, t in slots]
        result["axes"]["date_and_header_times"] = audit_axis(timestamps, 600, True)
        result["records_per_source_day"] = [
            {"excel_row": r + 2, "source_date": str(frame.iat[r, 0]),
             "timestamp_slots": len(slots),
             "nonblank_values": sum(not is_blank(frame.iat[r, c]) for c, _ in slots)}
            for r in range(len(frame))]
        result["notes"].append("源日期记录数与自然日记录数分别报告；0:00+1 明确落在次日。数值缺失不等于时间标签缺失。")
    else:
        if any(d is not None for d in dates):
            result["axes"]["explicit_row_dates"] = audit_axis([epoch(d) for d in dates], 86400, True)
        for i, h in enumerate(headers):
            if str(h) in {"时间", "时刻", "预报时刻"}:
                result["axes"][f"column_{i + 1}_clock_offsets"] = audit_axis(
                    [clock_seconds(v) for v in frame.iloc[:, i]], 600)
                if not any(d is not None for d in dates):
                    result["undated_record_count"] = len(frame)
                    result["notes"].append(f"{TODO}：仅有时刻，没有日历日期；记录数按未注明日期的序列报告。")
    # 区间标签原样展示，不擅自把区间起点、终点或跨日后缀选作时间戳。
    intervals = [str(h) for h in headers if isinstance(h, str) and ":" in h and "-" in h]
    for i, h in enumerate(headers):
        if "时间段" in str(h):
            intervals.extend(str(v) for v in frame.iloc[:, i] if not is_blank(v))
    if intervals:
        result["interval_label_counts"] = dict(Counter(intervals))
        result["notes"].append(f"{TODO}：区间标签采用起点还是终点作为索引及跨日后缀作用范围；区间时间戳检查未执行。")
    if not result["axes"]:
        result["notes"].append(f"{TODO}：无可直接解析的点时间轴，时间戳重复、缺口和逐日数量不可判定。")
    result["notes"].append(f"{TODO}：参考间隔为点序列 600 秒、日期 86400 秒；适用性及边界覆盖范围需确认，未修正数据。")
    return result
