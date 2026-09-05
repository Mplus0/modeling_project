# 华数杯 C 题建模代码

本项目用于实现 C 题“面向算电协同的多目标调度优化研究”。当前按模块逐步开发第一问，已完成原始数据读取与一致性验证。

## 环境配置

当前使用 Python 3.11，Conda 环境名称为 `modeling_project`：

```bash
conda activate modeling_project
python -m pip install -r requirement.txt
```

`gurobipy` 用于后续 MILP 调度模型。安装 Python 包不等于获得求解许可，正式求解前需确认本机 Gurobi License 可用。

## 项目结构

```text
modeling _project/
├── data/
│   └── raw/                    原始附件数据
├── outputs/                    预测、调度、指标和图表输出
├── scripts/
│   ├── 01_check_data.py       数据读取与验证入口
│   ├── 02_build_demand.py     构造并导出 GPU 需求序列
│   └── 03_run_forecast.py     参数选择与最终预测入口
├── src/
│   ├── config.py              路径、区域和时间边界
│   ├── data_loader.py         六个工作簿的数据读取
│   ├── data_validator.py      原始数据一致性检查
│   ├── demand_builder.py      小时级 GPU 新增需求序列
│   ├── forecast.py            多时间尺度 GPU 需求预测
│   └── metrics.py             需求与模型评价指标
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

也可不激活环境直接运行：

```bash
conda run -n modeling_project python scripts/01_check_data.py
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
```

`forecast_metrics.csv` 包含整体、区域、任务类型和区域任务组合共 28 行指标。某一分组的实际需求总和为 0 时，其 WAPE 记为空值，MAE 与 RMSE 仍正常计算。

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
5. 调度可行域与 Overlap
6. 两阶段 MILP 调度
7. 独立结果验算与图表输出

运行代码时请将工作目录切换到项目根目录。原始附件保留在 `data/raw`，生成结果统一写入 `outputs`。
