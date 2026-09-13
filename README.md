# 2026 全国大学生数学建模竞赛 C 题：微网与外部电网电力调控策略

本仓库包含赛题的数据处理、Q1–Q4数学模型代码、数值验收、论文图表及提交结果。五份正式结果工作簿已保存在 `outputs/submissions/`。模型检验与临时文件独立存放，不作为竞赛提交文件。

## 1. 环境与依赖

使用独立 Conda 环境 `modeling_project`。依赖文件实际名称为 **`requirement.txt`**，包含 pandas、NumPy、openpyxl、Matplotlib、SciPy、scikit-learn 和 PySCIPOpt；优化器通过 PySCIPOpt 调用 SCIP，不需要 Gurobi。

```powershell
# 仅在尚未创建环境时执行
conda create -n modeling_project python pip
conda run -n modeling_project python -m pip install -r requirement.txt
```

仓库没有 Python、SCIP及依赖包的完整版本锁文件，不能据此保证跨版本逐位复现。若使用原运行环境，请保留其版本。无需修改 shell 启动配置。

## 2. 仓库结构

```text
.
├── requirement.txt               # Python依赖清单，未锁版本
├── 赛题及预设实现方案/            # 赛题材料与文档
├── data/
│   ├── raw/                      # 官方附件，只读
│   └── processed/                # 标准化输入CSV
├── src/
│   ├── common/                   # 加载、时间解析、审计与预处理
│   ├── q1/                       # 单日优化、一级/二级比较、模板与绘图
│   ├── q2/                       # 历史预测、风险修正、因果滚动执行
│   ├── q3/                       # 可信度融合、联合场景、CVaR与年度实验
│   ├── q4/                       # 动态电价适配、年度复核与最终导出
│   └── analysis/                 # 消融、检验汇总及Vdk诊断索引
├── scripts/                      # 分阶段命令行入口，见下表
├── tests/                        # unittest测试
└── outputs/
    ├── submissions/              # 五份正式提交Excel
    ├── data_quality/             # 数据审计与预处理报告
    ├── schedule/                 # Q1正式调度
    ├── metrics/                  # Q1指标、Q2相似性指标
    ├── q2/                       # Q2全年计划、执行与验收
    ├── q3/                       # Q3最终结果、搜索与参考实验
    ├── q4/                       # Q4-2及固定参数Q4-3结果
    ├── comparison/               # Q1词典序比较、Q2版本比较及历史存档
    ├── model_validation/         # 消融、Vdk及最终导出验收
    └── figures/                  # 当前分支的Q1、Q2论文图片
```

仓库没有统一 `main.py`，也没有独立的 `config/` 或 `environment.yml`；参数在相应模块中定义。目录树省略空占位目录、缓存及临时文件。

## 3. 输入数据

| 原文件（相对 `data/raw/`） | 用途 | 标准化输出（相对 `data/processed/`） |
|---|---|---|
| `附件1.xlsx` | Q1的144个时段：电价、负荷、光伏预测 | `q1_input.csv`，144行 |
| `附件2.xlsx` | 历史负荷与实际光伏，365天×144时段 | `historical_power.csv`，52560行 |
| `附件3.xlsx` | 每日00/06/12/18发布、每次未来24小时光伏预报 | `pv_forecast_hourly.csv`，35040行 |
| `附件4.xlsx` | 历史动态电价 | `electricity_price.csv`，52560行 |
| `附件5/result1.xlsx`、`result2.xlsx`、`result3.xlsx`、`result4-2.xlsx`、`result4-3.xlsx` | 官方输出模板 | 不参与预处理；仅复制后填写 |

原始附件只读，预处理保留源日期和时间标签。`0:00+1`按次日00:00解析；附件3仅在验证每天四个发布时间结构后补齐展示省略的日期。预处理不插值、裁剪或删除样本。

功率单位为kW，10分钟电量为 `功率 × 10/60` kWh；电价为元/kWh，费用为元。预报CSV保留小时分辨率，Q3在模型层构造所需10分钟预测。Q2/Q3使用附件1日内电价，Q4使用附件4动态电价。

## 4. 运行入口

所有命令在仓库根目录执行。下表为便于阅读使用 `python`；在本项目环境中实际调用方式为：

```powershell
conda run --no-capture-output -n modeling_project python -B -X utf8 scripts/18_analyze_q3_information_value.py
```

即将表中的 `python` 替换为 `conda run --no-capture-output -n modeling_project python -B -X utf8`。以下是入口说明，不是需要依次执行的批处理清单。年度求解和绘图会写入结果，最终提交副本应以现有文件为准。

### 数据、Q1和Q2

| 命令 | 实际行为 |
|---|---|
| `python scripts/01_check_data.py` | 只读检查官方Excel，写入 `outputs/data_quality/`；可选 `--raw-dir`指定输入目录 |
| `python scripts/02_preprocess.py` | 从附件1–4生成四份标准化CSV及预处理报告 |
| `python scripts/03_run_q1.py` | 求解Q1并生成一级/二级比较；首次生成正式结果，已有三份完整Q1结果时仅更新诊断并保护正式文件 |
| `python scripts/04_plot_q1.py` | 读取Q1结果，生成五组PNG/PDF，不求解 |
| `python scripts/05_run_q2.py` | Q2全年预测、日前计划及实际滚动执行，写全年结果和result2；可选 `--skip-workbook`不写Excel |
| `python scripts/05_run_q2.py --benchmark` | 仅运行2月1日，输出到独立基准目录 |
| `python scripts/06_plot_q2_lag_similarity.py` | 生成1–14日滞后相似性CSV和PNG/PDF，不求解 |

### Q3与Q4

| 命令 | 实际行为与前置条件 |
|---|---|
| `python scripts/07_run_q3_single.py --alpha 0.85 --lambda 0.25 --days 3` | 默认从2025-03-20运行连续三日测试；支持 `--start-date`、`--initial-soc`、`--output-dir`；结果为测试/参考用途 |
| `python scripts/08_run_q3_annual.py --alpha 0.85 --lambda 0.25` | 先与已有三日参考对比，再运行单参数全年；`--regression-only`只执行三日回归，仍会求解 |
| `python scripts/09_run_q3_parameter_search.py --validate-only` | 只验证已有 `reference_a0.90_l0.50`；不重跑搜索 |
| `python scripts/09_run_q3_parameter_search.py --workers 1` | Q3的20组串行实验入口，逐组校验恢复并统一评分；属于已完成实验的复现工具 |
| `python scripts/10_run_q3_final.py --check-only` | 只检查冻结winner与官方模板，不验收全部最终轨迹，不求解 |
| `python scripts/10_run_q3_final.py` | 读取已有搜索选择，固定0.85/0.25重新运行全年，验收后写最终明细、论文表和result3 |
| `python scripts/11_smoke_q4.py --days 3` | Q4-2/Q4-3连续三日测试，写入 `outputs/q4/smoke/` |
| `python scripts/12_run_q4_2.py` | Q4-2年度计算，写入 `outputs/q4/q4_2/`，不导出Excel |
| `python scripts/13_run_q4_3_reference.py` | 固定0.85/0.25年度计算，写入 `outputs/q4/reference/q4_3_a0.85_l0.25/`，不导出Excel |
| `python scripts/14_run_q4_3_search.py --help` | 查看保留的旧Q4搜索入口参数；当前最终流程不执行该搜索 |
| `python scripts/19_precheck_q4_export.py` | 重跑定向测试、只读年度验收及临时Excel验证，不求解；报告及非提交副本写入 `outputs/model_validation/final_export_precheck/` |

Q3最终入口依赖已有搜索排名、winner摘要与逐日结果，不是从空目录直接运行的独立脚本。Q4-3最终参数固定沿用Q3，不要求Q4重新搜索；历史reference标签保留，正式采用资格见 `outputs/model_validation/q4_reference_acceptance.json`。

### 最终Excel导出

以下命令只读取已有结果并复制填写模板，不运行优化器：

```powershell
conda run --no-capture-output -n modeling_project python -B -X utf8 scripts/15_write_q4_results.py --variant 2 --human-approved
conda run --no-capture-output -n modeling_project python -B -X utf8 scripts/15_write_q4_results.py --variant 3 --human-approved
```

两份result4已生成，因此在当前提交目录重复执行会因禁止覆盖而拒绝。导出要求人工批准、formal年度验收、protected SHA一致；variant 3还须通过独立团队确认记录。验收记录写入 `outputs/model_validation/final_export/`，不写回正式源目录。预检脚本也会因result4已存在而给出覆盖阻断，这不表示现有Excel验收失败。

模板按已确认的slot原行序写入，保留原标签；模型slot1为00:00–00:10，模板首区间文字为0:10–0:20，不移动数值。充放电每24个连续slot汇总，填写外部充电 `x_real+q_real` 与实际放电 `z_real`。Q3/Q4-3调整表填写三轮累计净变化及净调整费，不填写最终合同量。

### 模型检验与测试

`python scripts/18_analyze_q3_information_value.py`只显示已验证Vdk索引，不重新计算信息价值。`python scripts/16_run_model_validation.py --help`可查看保留的实验入口；该入口限制reference分支，并会更新汇总文件。最终整理后的检验材料应直接从结果目录读取，Q2-A、Q4-A停止实验不再运行。

```powershell
# 导出门槛定向测试
conda run -n modeling_project python -B -X utf8 -m unittest discover -s tests -p test_q4_submission_gate.py -v
# 完整测试入口：应在独立复现副本运行
conda run -n modeling_project python -B -X utf8 -m unittest discover -s tests -v
```

完整测试包含求解、绘图和旧冻结清单检查，不是只读操作；绘图测试可能改写图片，新增输出也可能与历史全目录清单冲突。不要在冻结提交副本直接批量运行；当前验收依据见各结果目录的JSON，而非宣称全部历史测试始终通过。

## 5. 模型实现概要

四问均通过PySCIPOpt/SCIP求解连续线性规划。共用储能能量平衡、SOC上下界、充放电上限、光伏分配及负荷供给约束；允许弃光，不增加二元充放电互斥约束。词典序逐级求解并锁定前级目标，不用加权和替代优先级。

| 问题 | 主要方法、目标与差异 |
|---|---|
| Q1 | 144时段确定性优化；先最小购电费用，再最小储能吞吐量；日初与日末SOC均为6000kWh |
| Q2 | 因果历史回测选负荷/PV预测窗口，历史净负荷残差作Type-1分位数风险修正；日前最小购电费再最小吞吐量，计划末SOC等于当天初SOC。实际逐slot固定合同，按紧急购电费、相对当天初SOC的单侧终端缺口、吞吐量依次最小化；跨日传递真实SOC |
| Q3 | 00/06/12/18更新；历史误差确定光伏新旧预测可信度，成对残差构造联合场景。计划目标为购电/调整费用、期望紧急费用及加权CVaR之和，再最小平均吞吐量；无计划终端恢复约束。实际依次最小紧急费用、对最新计划场景终态期望的绝对偏差、吞吐量 |
| Q4-2 / Q4-3 | 分别复用Q2/Q3运行机制，历史同星期选窗预测动态电价，用已观测累计价格与基线之比更新未来价格；按真实动态价格结算。Q4-3固定使用团队确认的0.85/0.25 |

## 6. 当前参数

| 参数 | 值与定义 | 实现位置 |
|---|---|---|
| 时段与年度范围 | 10分钟，144slot/天；2025-02-01至12-31，共334天 | `src/q2/forecasting.py` |
| 充/放电效率 | 各0.90 | `src/q1/optimizer.py` |
| 初始SOC、上下界 | 首日6000kWh；1200–10800kWh；后续传递真实终态 | `src/q1/optimizer.py`及年度循环 |
| 单时段充/放电上限 | `5000 × 10/60` kWh；放电上限作用于实际送达负载的电量 | `src/q1/optimizer.py` |
| 负荷/PV候选窗口 | 同星期1/2/3/4周；连续3/5/7/14日 | `src/q2/forecasting.py` |
| 风险分位数 | Type-1，τ=0.8 | `src/q2/risk.py` |
| Q3可信度窗口 / 场景窗口 | 最近7日 / 最多最近14日；当前场景等概率 | `src/q3/confidence.py`、`scenarios.py` |
| Q3可信度ε / Q4价格ε | `1e-8` / `1e-12` | `src/q3/confidence.py`、`src/q4/price_forecasting.py` |
| Q3最终及Q4-3采用参数 | α=0.85，λ=0.25 | `src/q3/final.py`及Q4确认记录 |
| Q3已完成搜索集合 | α∈{0.80,0.85,0.90,0.95}；λ∈{0,0.25,0.5,1,2} | `src/q3/parameters.py` |
| Q3搜索Score | 全20组统一Min-Max；费用/紧急slot数/日费用总体标准差权重0.5/0.3/0.2，ddof=0 | `src/q3/search.py` |
| 紧急电费、合同调整系数 | 紧急5倍；增购1.5倍、减购退款0.5倍 | Q2/Q3优化器 |
| 数值容差 | SCIP feastol=`1e-9`；独立验收及有效紧急slot阈值=`1e-6` | Q1/Q2/Q3优化器 |
| 词典序目标锁 | Q1为一级费用等式锁；Q2/Q3前级费用锁±`1e-7`；Q2终端缺口锁±`1e-7` | Q1/Q2/Q3优化器及Q2 rolling模块 |

代码未显式设置SCIP的MIPGap或TimeLimit；不将未配置项写成已采用参数。

## 7. 输出与论文材料

### 正式提交

`outputs/submissions/`包含：`result1.xlsx`、`result2.xlsx`、`result3.xlsx`、`result4-2.xlsx`、`result4-3.xlsx`。它们是官方模板的填写副本；`data/raw/附件5/`保持原件。

| 内容 | 当前路径 |
|---|---|
| Q1调度 / 指标 | `outputs/schedule/q1_schedule.csv`、`outputs/metrics/q1_metrics.json` |
| Q2全年轨迹与指标 | `outputs/q2/q2_actual_schedule.csv`、`q2_plan_schedule.csv`、`q2_daily_metrics.csv`、`q2_metrics.json` |
| Q3最终轨迹、指标及论文表 | `outputs/q3/final/`；其中 `q3_final_validation.json`为最终验收，`q3_paper_summary.md`为论文摘要 |
| Q4-2全年结果 | `outputs/q4/q4_2/` |
| Q4-3最终采用结果 | `outputs/q4/reference/q4_3_a0.85_l0.25/` |
| Q4提交验收 | `outputs/model_validation/final_export/q4_2_submission_validation.json`、`q4_3_submission_validation.json` |
| 数据质量 | `outputs/data_quality/` |
| Q1一级/二级诊断 | `outputs/comparison/q1_primary_only_schedule.csv`、`q1_secondary_comparison.json`、`q1_secondary_comparison.md` |
| 论文模型检验总表 | `outputs/model_validation/summary/model_validation_summary.csv`、`model_validation_paper_summary.md` |
| Q3可信度消融 | `outputs/model_validation/q3_confidence_ablation/` |
| Q3信息价值Vdk | `outputs/model_validation/q3_information_value/`，已验证外部诊断的聚合结果与来源索引；当前显示入口不重算逐次Vdk |
| Q1论文图 | `outputs/figures/q1/`，五组PNG/PDF，索引见该目录 `README.md` |
| Q2论文图 | `outputs/figures/q2/q2_lag_similarity.png`及同名PDF |

Q3-C/D全年消融、Vdk及正式可行性验收可用于论文。Vdk是条件调整经济价值，不同更新时域重叠，其总和不等于全年真实节省。Q2-A、Q4-A未形成有效全年消融结果，仅保留审计，不纳入正式定量比较。

`outputs/q3/single/`、`outputs/q3/annual/`、各`smoke/`、`diagnostics/`、`outputs/comparison/archive/`及预检`tmp/`属于参考、诊断或历史材料；其中 `NOT_FOR_SUBMISSION_*.xlsx`不是正式提交文件。当前分支图片目录仅有Q1/Q2图片，不据其他分支的历史任务声称已有Q3/Q4绘图入口。

## 8. 复现建议

1. 保留当前提交副本，在独立仓库副本准备 `modeling_project` 环境，按 `requirement.txt`安装依赖。
2. 核对附件1–4及附件5五份模板路径；先审计，再预处理，检查四份CSV的行数、时间轴和单位。
3. 按需选择Q1、Q2、Q3或Q4入口。Q3最终运行需先具备已验证搜索结果；Q4-3直接使用固定参数入口，不执行旧Q4参数搜索。年度入口会重新求解，不能用于单纯查看结果。
4. 先查看CSV、指标和验收JSON，再检查Excel。Q4导出前运行预检，只在无目标文件且人工验收通过时执行导出命令；当前五份提交已齐全，无需重复导出。
5. 按上表定位正式工作簿、论文图表和检验材料。不要混用历史轨迹、失败实验或临时Excel。

各阶段保存SHA-256用于检测原数据及受保护结果变化；历史protected清单可能覆盖其他问题的结果和图片。跨环境重建、重绘或重算后应核对差异来源，不能跳过校验或把旧验收记录当作新结果证明。仓库依赖未锁版本，复现须同时检查求解状态、约束残差和前级目标保留误差，不能仅以Excel成功保存判断模型成功。
