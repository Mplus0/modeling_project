"""reference只读验收及两项单变量消融，输出与正式结果隔离。"""

from contextlib import contextmanager
import json
from pathlib import Path
import subprocess
from time import perf_counter
import traceback

import numpy as np
import pandas as pd

from src.common.data_loader import file_hash
from src.q2.forecasting import load_daily_inputs
from src.q2.optimizer import VALIDATION_TOL, validate_schedule
from src.q3.annual import FORMAL_DATES, ANNUAL_LABEL, validate_annual
from src.q3.forecast import load_hourly_forecasts
from src.q4.metrics import load_outputs
from src.q4.validation import validate_outputs
from src.analysis.ablation_adapters import q2_runner, run_q3_direct

Q4_REFERENCE = "outputs/q4/reference/q4_3_a0.85_l0.25"
DETAILS = ("actual_schedule", "daily_metrics", "forecast_updates", "confidence", "plan_updates", "scenarios_summary")


def save_json(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(content, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def read_csv(path):
    return pd.read_csv(path, float_precision="round_trip")


def branch_check(root):
    def git(*args):
        return subprocess.check_output(["git", *args], cwd=root, text=True, encoding="utf-8").strip()
    branch, head = git("branch", "--show-current"), git("rev-parse", "HEAD")
    if branch != "reference":
        raise RuntimeError(f"仅允许reference分支，当前为{branch}")
    return {"branch": branch, "head": head}


def frozen_hashes(root):
    # 保护全部数据、正式源码与既有输出；仅本实验目录可新增或改变。
    files = [p for name in ("data", "src/common", "src/q1", "src/q2", "src/q3", "src/q4", "outputs")
             for p in (root / name).rglob("*") if p.is_file() and "__pycache__" not in p.parts
             and not p.is_relative_to(root / "outputs/model_validation")]
    files += list((root / "scripts").glob("*_q*.py"))
    return {p.relative_to(root).as_posix(): file_hash(p) for p in sorted(set(files))}


@contextmanager
def protect(root, directory):
    before = frozen_hashes(root)
    save_json(directory / "frozen_before.json", before)
    try:
        yield
    finally:
        after = frozen_hashes(root)
        changed = [p for p in sorted(before.keys() | after.keys()) if before.get(p) != after.get(p)]
        save_json(directory / "integrity.json", {"unchanged": not changed, "changed": changed,
                                                  "before": before, "after": after})
        if changed:
            raise RuntimeError(f"模型检验冻结文件变化：{changed}")


def common_metrics(outputs, q2=False):
    a, d = outputs["actual_schedule"], outputs["daily_metrics"]
    emergency = a.emergency_purchase_kwh > VALIDATION_TOL
    plan_key = "planned_cost_yuan" if q2 else "plan_cost_00_yuan"
    total_key = "total_cost_yuan" if q2 else "total_actual_cost_yuan"
    # 紧急费用从已执行slot独立复算；全年std采用334个实际日费用的总体标准差。
    metrics = dict(total_actual_cost_yuan=float(d[total_key].sum()),
                   plan_cost_yuan=float(d[plan_key].sum()),
                   emergency_purchase_kwh=float(a.emergency_purchase_kwh.sum()),
                   emergency_cost_yuan=float(5 * (a.price_yuan_per_kwh * a.emergency_purchase_kwh).sum()),
                   emergency_slot_count=int(emergency.sum()), emergency_day_count=int(a.loc[emergency, "date"].nunique()),
                   daily_cost_std_yuan=float(d[total_key].std(ddof=0)))
    if not q2:
        metrics.update(adjustment_cost_yuan=float(d.adjustment_cost_total_yuan.sum()),
                       final_soc_kwh=float(a.soc_real_end_kwh.iloc[-1]),
                       simultaneous_slots=int(((a.x_real_kwh + a.q_real_kwh > VALIDATION_TOL) &
                                               (a.z_real_kwh > VALIDATION_TOL)).sum()))
    return metrics


def accept_reference(root):
    directory = root / "outputs/model_validation"
    with protect(root, directory / "reference_integrity"):
        outputs, stored = load_outputs(root / Q4_REFERENCE)
        if not (stored["alpha"] == .85 and stored["lambda"] == .25 and stored["formal"] is True
                and stored["passed"] is True and stored["days"] == 334 and stored["slots"] == 48096):
            raise ValueError("Q4 reference参数/全年范围/验收标记不符")
        checked = validate_outputs(outputs, 3, formal=True)
        metrics = common_metrics(outputs)
        mapping = {"plan_cost_yuan": "total_plan_cost_real_yuan", "adjustment_cost_yuan": "total_adjustment_cost_real_yuan",
                   "emergency_purchase_kwh": "total_emergency_purchase_kwh", "emergency_cost_yuan": "total_emergency_cost_yuan"}
        for name, value in metrics.items():
            if abs(value - stored[mapping.get(name, name)]) > VALIDATION_TOL:
                raise ValueError(f"Q4 reference指标复算不一致：{name}")
        a = outputs["actual_schedule"]
        soc = dict(initial_soc_kwh=float(a.soc_real_start_kwh.iloc[0]),
                   minimum_soc_kwh=float(min(a.soc_real_start_kwh.min(), a.soc_real_end_kwh.min())),
                   maximum_soc_kwh=float(max(a.soc_real_start_kwh.max(), a.soc_real_end_kwh.max())))
        for name, value in soc.items():
            if abs(value - stored[name]) > VALIDATION_TOL:
                raise ValueError(f"Q4 reference SOC复算不一致：{name}")
        rounds = outputs["plan_updates"].drop_duplicates(["date", "update_time"])
        statuses = {f"plan_{s}": rounds[f"{s}_status"].value_counts().to_dict() for s in ("primary", "secondary")}
        statuses.update({f"actual_{s}": a[f"rolling_{s}_status"].value_counts().to_dict() for s in ("primary", "secondary", "tertiary")})
        report = dict(**branch_check(root), **checked, **metrics, **soc, alpha=.85, **{"lambda": .25},
                      label="Q4-3 fixed-parameter accepted result", description="第四问固定沿用第三问风险参数进行动态电价分析",
                      original_label=stored["run_label"], solver_status_counts=statuses,
                      parameter_adoption="用户已明确确认：Q4-3继续采用现有0.85/0.25的334天验收结果，不再搜索",
                      source=Q4_REFERENCE, validation_tolerance=VALIDATION_TOL)
        save_json(directory / "q4_reference_acceptance.json", report)
        text = "# Q4 reference只读验收\n\nQ4-3 fixed-parameter accepted result。第四问固定沿用第三问风险参数进行动态电价分析。\n\n"
        text += "未重新求解，未修改历史PROVISIONAL标签；不是Q4重新搜索得到的最优参数。\n\n"
        text += "\n".join(f"- {k}: {v}" for k, v in report.items()) + "\n"
        (directory / "q4_reference_acceptance.md").write_text(text, encoding="utf-8")
        raw = a[["date", "slot", "price_yuan_per_kwh"]].rename(columns={"price_yuan_per_kwh": "real_price"})
        raw = raw.assign(charge_kwh=a.x_real_kwh + a.q_real_kwh, discharge_kwh=a.z_real_kwh)
        raw.to_csv(directory / "q4_reference_price_charge_slots.csv", index=False, encoding="utf-8-sig")
    report["frozen_sha256_unchanged"] = True
    save_json(directory / "q4_reference_acceptance.json", report)
    with (directory / "q4_reference_acceptance.md").open("a", encoding="utf-8") as handle:
        handle.write("\nSHA-256：全部受保护文件与验收前一致。\n")
    return report


def q3_validation(outputs, formal=True):
    if not outputs["daily_metrics"].alpha.eq(.85).all() or not outputs["daily_metrics"]["lambda"].eq(.25).all():
        raise ValueError("Q3消融固定参数不符")
    view = dict(outputs)
    for name in ("actual_schedule", "daily_metrics"):
        view[name] = outputs[name].assign(run_label=ANNUAL_LABEL)
    if formal:
        checked = validate_annual(view)
    else:
        a, d = view["actual_schedule"], view["daily_metrics"]
        checked = validate_schedule(a, "actual", float(d.soc_start_kwh.iloc[0]))
        if checked["max_violation"] > VALIDATION_TOL or len(a) != 144:
            raise ValueError("Q3-C轻量轨迹验收失败")
        for stage in ("primary", "secondary", "tertiary"):
            if not a[f"rolling_{stage}_status"].eq("optimal").all():
                raise ValueError("Q3-C实际状态不为optimal")
        plans = outputs["plan_updates"]
        if (not plans[["primary_status", "secondary_status"]].eq("optimal").all().all()
                or float(d.max_constraint_violation.max()) > VALIDATION_TOL
                or float(a.rolling_max_violation.max()) > VALIDATION_TOL):
            raise ValueError("Q3-C轻量计划或剩余时域验收失败")
    for row in outputs["confidence"].itertuples():
        if any(day >= row.date for day in row.history_dates.split(";") if day):
            raise ValueError("Q3可信度历史包含未来日期")
    return {"passed": True, "days": len(view["daily_metrics"]), "slots": len(view["actual_schedule"]), **checked}


def q2_validation(directory, reference, formal=True):
    names = ("predictions", "plan_schedule", "actual_schedule", "daily_metrics", "window_selection")
    out = {name: read_csv(directory / f"q2_{name}.csv") for name in names}
    a, p, d = [out[k] for k in ("actual_schedule", "plan_schedule", "daily_metrics")]
    dates = list(map(str, FORMAL_DATES if formal else FORMAL_DATES[:1]))
    if d.date.tolist() != dates or len(a) != len(dates)*144 or len(p) != len(a):
        raise ValueError("Q2-A日期或时段数不完整")
    maximum, cross, previous = 0., 0., 6000.
    for table in out.values():
        if table.isna().any().any() or not np.isfinite(table.select_dtypes(include=[np.number]).to_numpy()).all():
            raise ValueError("Q2-A存在缺失或非有限值")
    for stage in ("primary", "secondary", "tertiary"):
        if not a[f"rolling_{stage}_status"].eq("optimal").all():
            raise ValueError("Q2-A实际优化未全部optimal")
    if not d[["plan_primary_status", "plan_secondary_status"]].eq("optimal").all().all():
        raise ValueError("Q2-A计划优化未全部optimal")
    for row in d.itertuples():
        cross = max(cross, abs(row.soc_start_kwh - previous))
        maximum = max(maximum, abs(row.soc_start_kwh - previous), row.max_rolling_constraint_violation)
        for mode, table in (("plan", p), ("actual", a)):
            frame = table[table.date.eq(row.date)]
            if frame.slot.tolist() != list(range(1, 145)):
                raise ValueError("Q2-A slot不完整")
            objectives = (row.plan_primary_star, row.plan_secondary_objective) if mode == "plan" else ()
            checked = validate_schedule(frame, mode, row.soc_start_kwh, *objectives)
            maximum = max(maximum, checked["max_violation"])
        previous = float(a[a.date.eq(row.date)].soc_real_end_kwh.iloc[-1])
        maximum = max(maximum, abs(previous - row.soc_actual_end_kwh))
        day_actual = a[a.date.eq(row.date)]
        # 日指标必须与已执行轨迹逐日一致，不能只信任汇总JSON。
        for name, column in (("planned_cost_yuan", "planned_cost_slot_yuan"),
                             ("emergency_cost_yuan", "emergency_cost_slot_yuan"),
                             ("total_cost_yuan", "total_cost_slot_yuan"),
                             ("emergency_purchase_kwh", "emergency_purchase_kwh")):
            maximum = max(maximum, abs(getattr(row, name)-float(day_actual[column].sum())))
    if maximum > VALIDATION_TOL:
        raise ValueError(f"Q2-A独立复核违约：{maximum}")
    predictions = out["predictions"]
    if not predictions.risk_quantile_kwh.eq(0).all():
        raise ValueError("Q2-A风险修正非零")
    frozen = read_csv(reference / "q2_predictions.csv")
    columns = [c for c in predictions if c not in ("risk_quantile_kwh", "risk_adjusted_net_load_kwh")]
    pd.testing.assert_frame_equal(predictions[columns], frozen[frozen.date.isin(dates)][columns].reset_index(drop=True), check_exact=True)
    for row in out["window_selection"].itertuples():
        if any(day >= row.date for day in row.residual_dates.split("|")):
            raise ValueError("Q2-A风险历史包含未来日期")
    windows = read_csv(reference / "q2_window_selection.csv")
    pd.testing.assert_frame_equal(out["window_selection"], windows[windows.date.isin(dates)].reset_index(drop=True), check_exact=True)
    return out, dict(passed=True, days=len(d), slots=len(a), max_constraint_violation=maximum,
                     cross_day_soc_max_difference=cross, all_solver_statuses_optimal=True,
                     same_forecasts_and_windows=True, risk_correction_zero=True, past_only=True)


def comparison_table(left, right, left_name, right_name):
    # 差值=正式模型-消融；百分比以消融为分母，不把所有变化称为改善。
    return pd.DataFrame([dict(metric=k, **{left_name: v, right_name: right[k]}, difference=right[k]-v,
                              relative_change_percent=None if abs(v) <= VALIDATION_TOL else (right[k]-v)/v*100)
                         for k, v in left.items()])


def compare(directory, stem, left, right, labels, validation):
    table = comparison_table(left, right, *labels)
    table.to_csv(directory / f"{stem}_metrics.csv", index=False, encoding="utf-8-sig")
    rows = json.loads(table.to_json(orient="records", force_ascii=False, double_precision=15))
    save_json(directory / f"{stem}.json", dict(status="validated", labels=labels, metrics=rows,
              difference_definition=f"{labels[1]} - {labels[0]}", relative_denominator=labels[0],
              zero_denominator="abs(baseline)<=VALIDATION_TOL时百分比为null", ddof=0, validation_tolerance=VALIDATION_TOL))
    save_json(directory / f"{stem}_validation.json", validation)
    lines = [f"# {labels[0]} vs {labels[1]}", "", f"差值为{labels[1]}减{labels[0]}，百分比以{labels[0]}为分母；零基准记null。每日标准差ddof=0。", "",
             "| metric | " + " | ".join(labels) + " | difference | relative_change_percent |", "|---|---:|---:|---:|---:|"]
    for row in rows:
        lines.append("| " + " | ".join(str(row[k]) for k in ("metric", *labels, "difference", "relative_change_percent")) + " |")
    lines += ["", "数值只描述本次消融差异，不自动判定所有指标改善或统计显著性。"]
    (directory / f"{stem}_paper_summary.md").write_text("\n".join(lines)+"\n", encoding="utf-8")


def write_failure(directory, stem, failure):
    # 已停止的实验只生成失败说明，不伪造全年比较指标。
    integrity_path = directory / "run/integrity.json"
    unchanged = (json.loads(integrity_path.read_text(encoding="utf-8"))["unchanged"]
                 if integrity_path.exists() else False)
    save_json(directory / f"{stem}_validation.json", dict(passed=False, frozen_sha256_unchanged=unchanged, **failure))
    save_json(directory / f"{stem}.json", failure)
    (directory / f"{stem}_paper_summary.md").write_text(
        f"# {stem}\n\n实验停止：{failure['error']}\n\n未通过全年验收，无可供论文使用的全年消融比较值。未修改模型或重试。\n", encoding="utf-8")


def run_experiment(root, kind, smoke=False):
    stem = "q2_risk_ablation" if kind == "q2" else "q3_confidence_ablation"
    directory = root / "outputs/model_validation" / stem
    run_dir = directory / ("smoke" if smoke else "run")
    marker = run_dir / "attempt.json"
    if marker.exists():
        raise RuntimeError(f"已有运行记录，禁止自动重算：{marker}")
    save_json(marker, dict(status="started", experiment=kind, smoke=smoke, **branch_check(root)))
    tick = perf_counter()
    try:
        with protect(root, run_dir):
            if kind == "q2":
                q2_runner(root)(root, skip_workbook=True, benchmark=smoke)
                outputs, validation = q2_validation(run_dir, root / "outputs/q2", formal=not smoke)
                reference = {k: read_csv(root / f"outputs/q2/q2_{k}.csv") for k in ("actual_schedule", "daily_metrics")}
                if not smoke:
                    compare(directory, stem, common_metrics(outputs, True), common_metrics(reference, True),
                            ("Q2-A", "Q2-B"), validation)
            else:
                history, price = load_daily_inputs(root / "data/processed/historical_power.csv", root / "data/processed/q1_input.csv")
                issues = load_hourly_forecasts(root / "data/processed/pv_forecast_hourly.csv")
                outputs, timings = run_q3_direct(history, issues, price, FORMAL_DATES[:1] if smoke else FORMAL_DATES,
                                                6000., .85, .25, progress=lambda n, total, day: print(f"Q3-C {n}/{total}: {day}", flush=True))
                for key in ("actual_schedule", "daily_metrics"):
                    outputs[key] = outputs[key].assign(run_label="Q3-C ABLATION / NOT OFFICIAL")
                for name, frame in outputs.items():
                    frame.to_csv(run_dir / f"q3_{name}.csv", index=False, encoding="utf-8-sig")
                outputs = {k: read_csv(run_dir / f"q3_{k}.csv") for k in DETAILS}
                validation = q3_validation(outputs, formal=not smoke)
                updates = outputs["forecast_updates"]
                if not updates.confidence_rho.eq(1).all() or not np.array_equal(updates.updated_forecast_kwh, updates.new_raw_forecast_kwh):
                    raise ValueError("Q3-C没有直接采用新预测")
                save_json(run_dir / "timings.json", timings)
                if not smoke:
                    reference = {k: read_csv(root / f"outputs/q3/final/q3_{k}.csv") for k in DETAILS}
                    q3_validation(reference)
                    compare(directory, stem, common_metrics(outputs), common_metrics(reference), ("Q3-C", "Q3-D"), validation)
                    by_update = []
                    for label, out in (("Q3-C", outputs), ("Q3-D", reference)):
                        plans = out["plan_updates"]
                        for hour in ("06:00", "12:00", "18:00"):
                            p = plans[plans.update_time.eq(hour)]
                            by_update.append(dict(model=label, update_time=hour, increase_kwh=float(p.increase_kwh.sum()),
                                                  decrease_kwh=float(p.decrease_kwh.sum()), adjustment_cost_yuan=float(p.adjustment_cost_yuan.sum())))
                    pd.DataFrame(by_update).to_csv(directory / f"{stem}_by_update.csv", index=False, encoding="utf-8-sig")
        validation["frozen_sha256_unchanged"] = True
        save_json(run_dir / "validation.json", validation)
        if not smoke:
            save_json(directory / f"{stem}_validation.json", validation)
        save_json(marker, dict(status="validated", smoke=smoke, runtime_seconds=perf_counter()-tick))
        return validation
    except Exception as error:
        # 数值或模型验收失败只记录并停止该实验，不重试、不改容差或目标。
        context = []
        tb = error.__traceback__
        while tb:
            local = tb.tb_frame.f_locals
            context.append(dict(function=tb.tb_frame.f_code.co_name,
                                **{k: str(local[k]) for k in ("date", "day", "slot", "hour") if k in local}))
            tb = tb.tb_next
        failure = dict(status="failed", smoke=smoke, error=str(error), context=context,
                       traceback=traceback.format_exc(), runtime_seconds=perf_counter()-tick)
        save_json(marker, failure)
        if not smoke:
            write_failure(directory, stem, failure)
        raise


def summary(root):
    base = root / "outputs/model_validation"
    rows, paper_tables = [], []
    for stem, label in (("q2_risk_ablation", "Q2-A vs Q2-B"), ("q3_confidence_ablation", "Q3-C vs Q3-D"),
                        ("q4_price_blind", "Q4-A vs Q4-B")):
        path = base / stem / "run/attempt.json"
        attempt = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"status": "not_run"}
        row = dict(experiment=label, status=attempt["status"], note=attempt.get("error", ""), path=str(base / stem))
        if stem == "q2_risk_ablation" and attempt.get("status") == "failed":
            row.update(status="stopped", note="未完成334天全年验收；按团队决定停止，部分运行数据不进入论文定量比较")
        if stem == "q4_price_blind":
            row.update(status="not included in formal quantitative comparison due to solver numerical failure",
                       note="未形成有效全年实验结果，不纳入正式定量比较；沿用既有Q4-3 reference")
        elif attempt["status"] == "validated":
            table = read_csv(base / stem / f"{stem}_metrics.csv")
            cost = table[table.metric.eq("total_actual_cost_yuan")].iloc[0]
            row.update(ablation_cost_yuan=float(cost.iloc[1]), formal_cost_yuan=float(cost.iloc[2]),
                       cost_difference_yuan=float(cost.difference), cost_change_percent=float(cost.relative_change_percent))
            paper_tables.append((base / stem / f"{stem}_paper_summary.md").read_text(encoding="utf-8"))
        rows.append(row)
    rows.extend([dict(experiment="Q3 Vdk", status="validated", note="external validated diagnostic；已从提交 c5c5bf959c8ef54828ac1618ea1ee97f4a7443e8 核对补回；本分支不重新计算。", path=str(base / "q3_information_value")),
                 dict(experiment="Q4 low/high price ratios", status="pending modeler confirmation", note="TODO: 需建模手确认低价/高价定义", path=str(base / "q4_reference_price_charge_slots.csv"))])
    directory = base / "summary"
    directory.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(directory / "model_validation_summary.csv", index=False, encoding="utf-8-sig")
    test_path = base / "tests/results.json"
    tests = json.loads(test_path.read_text(encoding="utf-8")) if test_path.exists() else None
    hash_path = base / "reference_integrity/frozen_before.json"
    unchanged = (frozen_hashes(root) == json.loads(hash_path.read_text(encoding="utf-8"))
                 if hash_path.exists() else None)
    save_json(directory / "model_validation_validation.json", dict(experiments=rows, all_requested_experiments_complete=False,
              q4_price_blind_definition_confirmed=True, formal_results_not_recomputed=True,
              frozen_sha256_unchanged=unchanged, regression_tests=tests))
    (directory / "model_validation_summary.md").write_text("# 模型检验汇总\n\n" + "\n\n".join(
        f"- {row['experiment']}: {row['status']}。{row['note']}\n  {row['path']}" for row in rows)
        + "\n\n" + "\n\n".join(paper_tables), encoding="utf-8")
    from src.analysis.paper_validation import write_paper_outputs
    write_paper_outputs(root)
