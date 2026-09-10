"""附件 1–4 的标准化预处理；结构不符即停止，不修补观测值。"""

from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd

from src.common.data_loader import discover_workbooks, file_hash, load_sheets
from src.common.data_validator import validate_sheet
from src.common.time_utils import audit_axis, clock_seconds, epoch, is_blank, parse_date


def require(condition, message):
    if not condition:
        raise ValueError(f"{message}；预处理已停止，未自动修复数据")


def check_axis(values, step, name):
    # 复用审计的时间轴规则，不排序、去重或补齐原序列。
    audit = audit_axis(values, step)
    require(not audit["unresolved_records"] and not audit["duplicate_extra_count"]
            and not audit["missing_timestamp_count"] and not audit["off_grid_timestamps"]
            and audit["interval_consistent"] is True, f"{name}时间轴不完整或不连续")


def check_sheet(sheet, shape, numeric_columns, allow_blank_dates=False):
    require(sheet["frame"].shape == shape, f"{sheet['sheet']}尺寸应为 {shape}")
    audit = validate_sheet(sheet)
    for column in audit["columns"]:
        i = column["excel_column"] - 1
        if not (allow_blank_dates and i == 0):
            require(column["missing_count"] == 0, f"{sheet['sheet']}第 {i + 1} 列存在缺失")
        if i in numeric_columns:
            require(column["numeric_count"] == shape[0] and column["nonfinite_count"] == 0,
                    f"{sheet['sheet']}第 {i + 1} 列含非数值、公式或非有限值")


def add_energy(frame, power_column, energy_column):
    # 10 分钟功率对应的电量：kW × (10/60) 小时 = kWh；价格不乘此系数。
    frame[energy_column] = frame[power_column] * (10 / 60)


def preprocess_q1(sheet):
    require(sheet["headers"] == ["时间", "电价", "小区负载", "光伏发电预测功率"], "附件 1 表头不符")
    check_sheet(sheet, (144, 4), {1, 2, 3})
    raw = sheet["frame"]
    offsets = [clock_seconds(v) for v in raw.iloc[:, 0]]
    check_axis(offsets, 600, "附件 1")
    require(offsets == list(range(600, 86401, 600)), "附件 1 应覆盖 00:10 至次日 00:00")
    result = pd.DataFrame({
        "slot": range(1, 145),
        # Excel time 对象仅序列化为时刻文本；已有字符串（含 +1）原样保留。
        "source_time": raw.iloc[:, 0].map(str),
        "price_yuan_per_kwh": raw.iloc[:, 1],
        "load_kw": raw.iloc[:, 2], "pv_forecast_kw": raw.iloc[:, 3],
    })
    add_energy(result, "load_kw", "load_kwh")
    add_energy(result, "pv_forecast_kw", "pv_forecast_kwh")
    return result


def preprocess_wide(sheet, value_name):
    require(str(sheet["headers"][0]).replace("\\", "") == "日期时间", "宽表日期表头不符")
    check_sheet(sheet, (365, 145), set(range(1, 145)))
    raw = sheet["frame"]
    dates = [parse_date(v) for v in raw.iloc[:, 0]]
    require(all(d is not None and d == d.normalize() for d in dates), "宽表日期不可解析或包含非零时刻")
    check_axis([epoch(d) for d in dates], 86400, sheet["sheet"])
    labels = sheet["headers"][1:]
    offsets = [clock_seconds(v) for v in labels]
    require(offsets == list(range(600, 86401, 600)), "宽表时间列必须为 00:10 至 0:00+1 的 144 个十分钟点")
    # 按原行列顺序展开；显式 +1 由公共解析器解释为次日，不删除跨年终点。
    result = pd.DataFrame({
        "datetime": [d + pd.Timedelta(seconds=t) for d in dates for t in offsets],
        "source_date": [d.date().isoformat() for d in dates for _ in labels],
        "source_time": [str(label) for _ in dates for label in labels],
        value_name: raw.iloc[:, 1:].to_numpy().ravel(),
    })
    check_axis([epoch(v) for v in result["datetime"]], 600, value_name)
    return result


def preprocess_forecast(sheet):
    expected_headers = ["日期", "预报时刻"] + [f"预报{h}小时" for h in range(1, 25)]
    require(sheet["headers"] == expected_headers, "附件 3 预报表头不符")
    check_sheet(sheet, (1460, 26), set(range(2, 26)), allow_blank_dates=True)
    raw = sheet["frame"]
    dates, filled_rows = [], []
    for start in range(0, len(raw), 4):
        block = raw.iloc[start:start + 4]
        day = parse_date(block.iat[0, 0])
        require(day is not None and day == day.normalize(), f"附件 3 第 {start + 2} 行缺少有效组首日期")
        clocks = [clock_seconds(v) for v in block.iloc[:, 1]]
        require(clocks == [0, 21600, 43200, 64800], f"附件 3 第 {start + 2} 行起必须按顺序包含 00、06、12、18 时")
        for offset, value in enumerate(block.iloc[:, 0]):
            if is_blank(value):
                filled_rows.append(start + offset + 2)
            else:
                require(parse_date(value) == day, f"附件 3 第 {start + offset + 2} 行日期与组首不一致")
        dates.append(day)
    check_axis([epoch(d) for d in dates], 86400, "附件 3 日期分组")
    # 全表 365 个四行组验证通过后才推导空白日期；原始 DataFrame 始终不变。
    issues = [d + pd.Timedelta(hours=h) for d in dates for h in (0, 6, 12, 18)]
    check_axis([epoch(d) for d in issues], 21600, "附件 3 发布")
    result = pd.DataFrame({
        "issue_datetime": [issue for issue in issues for _ in range(24)],
        "target_datetime": [issue + pd.Timedelta(hours=h) for issue in issues for h in range(1, 25)],
        "horizon_hour": list(range(1, 25)) * len(issues),
        "pv_forecast_kw": raw.iloc[:, 2:].to_numpy().ravel(),
    })
    # 不同发布时刻可预测同一目标；唯一键是发布时刻与预报步长的组合。
    require(not result.duplicated(["issue_datetime", "target_datetime"]).any(), "附件 3 存在重复发布/目标组合")
    return result, filled_rows


def run_preprocessing(raw_dir, processed_dir, report_path):
    raw_dir, processed_dir, report_path = map(Path, (raw_dir, processed_dir, report_path))
    sources = discover_workbooks(raw_dir)
    before = {p: file_hash(p) for p in sources}
    output_names = ["q1_input.csv", "historical_power.csv", "pv_forecast_hourly.csv", "electricity_price.csv"]
    targets = [processed_dir / name for name in output_names] + [report_path]
    for target in targets:
        resolved = target.resolve()
        require(raw_dir.resolve() not in resolved.parents and resolved != raw_dir.resolve(), "输出路径不能位于 data/raw 内")
        require(not target.is_symlink(), "输出文件不能是符号链接")
    # 附件 5 只计算哈希验证完整性，不加载、不预处理模板工作表。
    books = {n: list(load_sheets(raw_dir / f"附件{n}.xlsx")) for n in range(1, 5)}
    require([len(books[n]) for n in range(1, 5)] == [1, 2, 1, 1], "附件 1–4 的工作表数量不符")
    q1 = preprocess_q1(books[1][0])
    sheets = {s["sheet"]: s for s in books[2]}
    require(set(sheets) == {"小区负载", "光伏发电实际功率"}, "附件 2 工作表名称不符")
    historical = preprocess_wide(sheets["小区负载"], "load_kw")
    pv = preprocess_wide(sheets["光伏发电实际功率"], "pv_actual_kw")
    keys = ["datetime", "source_date", "source_time"]
    # 先验证两张表逐位置完全对齐，再组合；不使用可能丢行的内连接。
    require(historical[keys].equals(pv[keys]), "附件 2 负载与光伏时间标签不对齐")
    historical["pv_actual_kw"] = pv["pv_actual_kw"]
    add_energy(historical, "load_kw", "load_kwh")
    add_energy(historical, "pv_actual_kw", "pv_actual_kwh")
    forecast, filled_rows = preprocess_forecast(books[3][0])
    price = preprocess_wide(books[4][0], "price_yuan_per_kwh")
    require(historical[keys].equals(price[keys]), "附件 4 与附件 2 时间标签不对齐")
    outputs = dict(zip(output_names, (q1, historical, forecast, price)))
    for name, frame in outputs.items():
        require(not frame.isna().any().any(), f"{name}存在意外缺失")
    require(discover_workbooks(raw_dir) == sources and all(file_hash(p) == before[p] for p in sources), "原始文件在预处理期间发生变化")
    # 全部输入、输出验证通过后暂存 CSV，再替换目标文件；结构错误不会发布部分新数据。
    processed_dir.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix=".preprocess-", dir=processed_dir) as temporary:
        for name, frame in outputs.items():
            frame.to_csv(Path(temporary) / name, index=False, encoding="utf-8", date_format="%Y-%m-%d %H:%M:%S")
        for name in outputs:
            (Path(temporary) / name).replace(processed_dir / name)
    after = {p: file_hash(p) for p in sources}
    unchanged = before == after and discover_workbooks(raw_dir) == sources
    lines = ["# 标准化预处理摘要", "", "| 输入（数据行，不含表头） | 输出 | 输出行数 | 时间分辨率 | 缺失值 |",
             "|---|---|---:|---|---|",
             f"| 附件 1：144 | q1_input.csv | {len(q1)} | 10 分钟，原时刻标签 | 0 |",
             f"| 附件 2：两表各 365 × 144 | historical_power.csv | {len(historical)} | 10 分钟 | 0 |",
             f"| 附件 3：1460 × 24 | pv_forecast_hourly.csv | {len(forecast)} | 每 6 小时发布，预报步长 1 小时 | 0 |",
             f"| 附件 4：365 × 144 | electricity_price.csv | {len(price)} | 10 分钟 | 0 |", "",
             "附件 3：365 个日组均按 00、06、12、18 时排列；1460 个唯一发布时刻，每次 24 条预报。",
             f"仅在派生时间中补全 {len(filled_rows)} 个展示用空白日期：位置为每个四行日组内原日期为空的非首行，取该组首行日期；原始表未变。", "",
             "功率原值保留，新增电量列 = 功率 × (10/60)；电价原值保留。源时间字符串保留，Excel time 对象序列化为 HH:MM:SS；不构造区间标签。",
             "0:00+1 属次日。目标时间 = 发布时刻 + horizon_hour 小时；目标时间可跨发布时刻重复，发布/目标组合唯一。未重采样或插值。",
             "附件 5 未加载、未预处理；仅纳入哈希完整性检查。没有删除、裁剪或归一化任何数值。", "",
             f"SHA-256 完整性：{'通过' if unchanged else '失败'}（全部 {len(sources)} 个官方工作簿处理前后对比）。", "",
             "| 原始文件 | 处理前 SHA-256 | 处理后 SHA-256 |", "|---|---|---|"]
    lines.extend(f"| {p.relative_to(raw_dir)} | {before[p]} | {after[p]} |" for p in sources)
    lines.extend(["", "未解决的建模确认事项：无（仅执行本阶段已明确的标准化规则）。", ""])
    # 原子替换报告，不经由已有文件链接写入其他文件。
    with TemporaryDirectory(prefix=".preprocess-report-", dir=report_path.parent) as temporary:
        staged = Path(temporary) / "summary.md"
        staged.write_text("\n".join(lines), encoding="utf-8")
        staged.replace(report_path)
    require(unchanged, "原始文件 SHA-256 完整性校验失败")
    return outputs, filled_rows
