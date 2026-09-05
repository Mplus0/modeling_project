# 华数杯 C 题建模代码

本项目用于实现 C 题“面向算电协同的多目标调度优化研究”。第一问的数据、预测、两阶段调度、独立验算和结果生成模块均已实现。

## 环境配置

当前使用 Python 3.11，Conda 环境名称为 `modeling_project`：

```bash
conda activate modeling_project
python -m pip install -r requirement.txt
```

调度模型使用开源的 SCIP 求解器及其 Python 接口 `pyscipopt`，不需要申请 Gurobi 许可证。依赖只安装在 `modeling_project` 虚拟环境中。

## 项目结构

```text
modeling _project/
├── data/
│   └── raw/                    原始附件数据
├── outputs/                    预测、调度、指标和图表输出
├── scripts/
│   ├── 01_check_data.py       数据读取与验证入口
│   ├── 02_build_demand.py     构造并导出 GPU 需求序列
│   ├── 03_run_forecast.py     参数选择与最终预测入口
│   ├── 04_run_schedule.py     两阶段调度与结果验算
│   └── 05_generate_report_outputs.py  指标与图表生成
├── src/
│   ├── config.py              路径、区域和时间边界
│   ├── data_loader.py         六个工作簿的数据读取
│   ├── data_validator.py      原始数据一致性检查
│   ├── demand_builder.py      小时级 GPU 新增需求序列
│   ├── feasible_domain.py     稀疏调度可行域
│   ├── forecast.py            多时间尺度 GPU 需求预测
│   ├── metrics.py             需求与模型评价指标
│   ├── overlap.py             非整数持续时间重叠系数
│   ├── result_validator.py    调度结果独立验算
│   ├── scheduler_stage1.py    第一阶段调度模型
│   ├── scheduler_stage2.py    第二阶段峰值优化
│   └── visualization.py       预测与调度图表
├── main.py                    第一问完整复现入口
├── 赛题及预设实现方案/          题面、附件说明和代码方案
└── requirement.txt
```

## 当前模块

### 数据读取

`load_raw_data()` 默认从 `data/raw` 读取六个工作簿的建模数据页，返回 `RawDataBundle`。加载过程不清洗或修改原始数据。

```python
from src.data_loader import load_raw_data

data = load_raw_data()
print(data.tasks.shape)
```

也可指定其他数据目录：

```python
data = load_raw_data("path/to/raw_data")
```

### 数据验证

`validate_data()` 检查任务、区域容量、网络时延、任务功率映射和区域小时数据。验证不会修改 DataFrame。

```python
from src.data_loader import load_raw_data
from src.data_validator import validate_data

data = load_raw_data()
report = validate_data(data)

for warning in report.warnings:
    print(f"WARNING: {warning}")

report.raise_for_errors()
```

`region_time_data.xlsx` 中的 `GPU_Utilization_Percent` 是附件给出的基准运行指标，不是 GPU 容量硬输入。大于 100% 的记录只生成 warning，并报告数量、最大值和示例位置。

从项目根目录运行完整数据检查：

```bash
python scripts/01_check_data.py
```

后续优化结果必须根据任务调度重新计算：

```text
GPU_Utilization = GPU_Used / Available_GPU
GPU_Used <= Available_GPU
```

### GPU 需求序列

`build_demand_series()` 按任务到达时刻汇总 GPU 新增需求，并补齐没有任务的组合。结果固定包含 0–2399 小时、6 个区域和3类任务，共 43,200 行。

```python
from src.data_loader import load_raw_data
from src.demand_builder import build_demand_series

data = load_raw_data()
demand = build_demand_series(data.tasks)
```

`aggregate_region_demand()` 和 `aggregate_system_demand()` 分别生成区域逐时总需求和系统逐时总需求。这里的需求是任务到达产生的原始新增 GPU 需求，不是调度后的 GPU 利用率。

由你运行需求序列导出：

```bash
python scripts/02_build_demand.py
```

脚本通过原始数据验证后生成：

```text
outputs/forecast/demand_series.csv
outputs/forecast/region_demand_series.csv
outputs/forecast/system_demand_series.csv
outputs/metrics/demand_statistics.csv
```

需求统计表共 28 行，包括系统、6 个区域、3 类任务和 18 个区域任务组合。每行基于对应的完整 2400 小时序列计算 `count`、`mean`、`std`、`min`、`median`、`max`、`sum` 和 `zero_ratio`，其中 `std` 为总体标准差。

### GPU 需求预测

预测模型由长期均值、最近 24 小时均值和过去 7 天同小时均值加权组成。验证阶段一次性预测 2352–2375 小时，权重搜索步长为 0.05，并依次按 WAPE、MAE、RMSE 选择最优参数。最终预测使用 0–2375 小时历史直接预测 2376–2399，不递归使用预测值。

```python
from src.forecast import forecast_demand, select_forecast_weights

weights, validation_scores = select_forecast_weights(demand)
forecast = forecast_demand(demand, weights)
```

当前模块只实现点预测。预测区间与风险裕度尚无明确数学定义，因此未自行加入。

由你运行预测流程：

```bash
python scripts/03_run_forecast.py
```

脚本将生成：

```text
outputs/forecast/forecast_2376_2399.csv
outputs/forecast/forecast_parameters.json
outputs/forecast/validation_weight_search.csv
outputs/metrics/forecast_metrics.csv
outputs/metrics/forecast_component_diagnostics.csv
outputs/metrics/forecast_series_diagnostics.csv
```

`forecast_metrics.csv` 包含整体、区域、任务类型和区域任务组合共 28 行指标。某一分组的实际需求总和为 0 时，其 WAPE 记为空值，MAE 与 RMSE 仍正常计算。

当前预测结果保留为 baseline。模型效果问题不作为代码错误，未经建模手确认不改变模型结构、权重口径、验证方式或参数选择指标。

两个诊断文件分别记录 LongTerm-only、ShortTerm-only、DailyPattern-only 的验证指标，以及18条 `Region × TaskType` 序列的验证 WAPE/MAE/RMSE、训练段 `zero_ratio`、均值、总体标准差和 lag=24/168 自相关。诊断结果不参与模型选择，也不修改 baseline。

### 调度可行域与 Overlap

`select_schedule_tasks()` 提取 2376–2399 小时实际到达的任务，并计算 `DurationHour` 和 `MaxDelayHour`。`build_feasible_domains()` 仅枚举同时满足网络时延、整点开工、任务时间窗、截止时刻和 2406 终端约束的 `(TargetRegion, StartHour)`。

实时推理任务的 `StartHour` 固定为 `ArrivalHour`。批量推理和 AI 训练任务的最早开工时刻取 `max(ArrivalHour, EarliestStartHour)`。若任一任务的可行域为空，函数立即报出 `TaskID` 和原因。

`precompute_overlaps()` 只保存大于 0 的小时重叠系数：

```text
overlaps[(TaskID, StartHour, Hour)]
active_options[(Region, Hour)]
```

当前可行域不提前加入 GPU、IT 功率或设施功率筛选，这三类约束将在 MILP 中统一建立。

### 最小调度 MILP

`build_minimal_schedule_model()` 只为可行域中的 `(TaskID, TargetRegion, StartHour)` 建立二元变量，并加入：

```text
每个任务恰好选择一个调度方案
每个 Region-Hour 的 GPU_Used <= Available_GPU
```

GPU 占用按 `GPU_Demand × Overlap` 计算，资源约束覆盖 2376–2405 小时。`add_power_constraints()` 在此基础上加入：

```text
NonAI_IT_Load_MW + AI_IT_Power <= Max_IT_Power_MW
PUE × Total_IT_Power <= Max_Facility_Power_MW
```

AI IT 功率严格使用 `power_mapping.xlsx` 的任务类型单位 GPU 功率。`add_waiting_objective()` 按方案建立归一化等待率目标，`build_stage1_model()` 组合全部硬约束与第一阶段目标。`solve_stage1()` 输出状态、目标值、运行时间和 MIPGap，`decode_schedule_solution()` 将二元决策解码为任务调度表。

### 第二阶段调度

`configure_stage2()` 在第一阶段最优解上加入：

```text
J1 <= (1 + delta) × J1_star
GPU_Used / Available_GPU <= U_max
```

随后以第一阶段解作为 Warm Start，并最小化 `U_max`。峰值约束时段可显式选择 `evaluation`（2376–2399）或 `resource`（2376–2405），代码不自行决定口径。

### 调度结果独立验算

`validate_schedule()` 不读取 SCIP 模型，直接根据最终任务表重新检查唯一调度、整点开工、到达时刻、实时任务、网络 SLA、Deadline 和 2406 终端约束，并重新计算完整的 180 条 Region-Hour 资源记录。

验算结果包含任务级与资源级 violations、汇总计数，以及 `GPU_Used`、GPU利用率、AI IT功率、总IT功率和设施功率明细。优化结果只有在 violations 为空时才允许进入正式结果输出。

### 指标与图表

`build_schedule_metrics()` 计算区域平均/峰值GPU利用率、全局峰值与P95利用率、等待时间、按时完成率、迁移率及区域流入流出数量。GPU利用率在指标表中以 0–1 比例保存。

`visualization.py` 实现方案中编号01–10的全部图表：4张预测图可直接由 baseline 输出生成，6张调度图在正式调度结果通过独立验算后生成。

预测结果已经存在时，可单独生成当前可用的指标和图表：

```bash
python scripts/05_generate_report_outputs.py
```

若尚无正式调度结果，该脚本只生成4张预测图；调度完成后会继续生成 `schedule_metrics.csv` 和6张调度图。

### 正式调度运行

正式参数已经确认并写入 `config.py`：

```text
epsilon = 1e-6
delta = 0.05
U_max 时段 = resource（2376–2405）
SCIP MIPGap = 0.001（0.1%）
单阶段 TimeLimit = 300 秒
```

直接运行：

```bash
python scripts/04_run_schedule.py
```

`--time-limit` 和 `--mip-gap` 可覆盖默认求解停止条件，只控制求解过程。成功后生成：

```text
outputs/schedule/stage1_solution.csv
outputs/schedule/stage2_solution.csv
outputs/schedule/task_schedule.csv
outputs/schedule/region_hour_resource.csv
outputs/schedule/stage1_summary.json
outputs/schedule/stage2_summary.json
outputs/metrics/validation_report.txt
outputs/logs/stage1_solver.log
outputs/logs/stage2_solver.log
```

从原始数据完整复现第一问：

```bash
python main.py --question 1
```

命令行参数 `--epsilon`、`--delta` 和 `--peak-hours` 仍可用于显式复现实验对照，但不会自动改变配置文件。

### 本次正式运行结果

- 调度任务数：538，完成率 100%；
- 第一阶段：`OPTIMAL`，`J1* = 0`，所有任务等待时间均为 0；
- 第二阶段：`GAPLIMIT`，`U_max = 0.562222`，最终 MIP Gap 为 0.0901%，满足预设的 0.1% 停止精度；
- 独立验算：SLA、Deadline、终端时刻、GPU、IT 功率及设施功率违规数均为 0；
- 2376–2405 时段内最大 GPU 利用率为 56.22%，最大 IT/设施功率利用率约为 99.97%。

`GAPLIMIT` 表示 SCIP 已达到预设相对间隙并正常停止，不表示求解失败。详细结果见 `outputs/schedule`、`outputs/metrics`、`outputs/figures` 和 `outputs/logs`。

### 已确认调度参数

- 第一阶段等待率分母 `epsilon = 1e-6`；
- 第二阶段服务目标允许恶化 `delta = 0.05`；
- 第二阶段 `U_max` 按2376–2405统计。

## 第一问统一口径

- 训练数据：0–2351 小时。
- 验证数据：2352–2375 小时。
- 最终预测：2376–2399 小时。
- 调度对象：2376–2399 小时实际到达的任务，不使用预测值生成任务。
- 资源约束检查：2376–2405 小时。
- 所有任务必须在 2406 时点前完成，不得占用第 2406 小时。
- GPU 容量使用 `Available_GPU`。
- 优化后的 AI IT 功率按 `power_mapping.xlsx` 重新计算。

## 开发顺序

1. 数据读取与验证（已完成）
2. GPU 需求序列构造（核心模块已完成）
3. 需求统计分析（核心模块已完成）
4. 多时间尺度需求预测（核心模块已完成）
5. 调度可行域与 Overlap（核心模块已完成）
6. 两阶段 MILP 调度（SCIP 版本及正式参数均已完成）
7. 独立结果验算、指标与图表模块（已完成）

运行代码时请将工作目录切换到项目根目录。原始附件保留在 `data/raw`，生成结果统一写入 `outputs`。
