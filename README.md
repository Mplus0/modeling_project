# 华数杯 C 题建模代码

本项目用于实现 C 题“面向算电协同的多目标调度优化研究”。当前按模块逐步开发第一问，已完成原始数据读取与一致性验证。

## 环境配置

建议使用 Python 3.11，并在独立 Conda 环境中安装依赖：

```bash
conda create -n huashu2026 python=3.11
conda activate huashu2026
python -m pip install -r requirement.txt
```

`gurobipy` 用于后续 MILP 调度模型。安装 Python 包不等于获得求解许可，正式求解前需确认本机 Gurobi License 可用。

## 项目结构

```text
modeling _project/
├── data/
│   └── raw/                    原始附件数据
├── outputs/                    预测、调度、指标和图表输出
├── scripts/                    分步骤运行入口
├── src/
│   ├── config.py              路径、区域和时间边界
│   ├── data_loader.py         六个工作簿的数据读取
│   └── data_validator.py      原始数据一致性检查
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

后续优化结果必须根据任务调度重新计算：

```text
GPU_Utilization = GPU_Used / Available_GPU
GPU_Used <= Available_GPU
```

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
2. GPU 需求序列构造
3. 需求统计分析
4. 多时间尺度需求预测
5. 调度可行域与 Overlap
6. 两阶段 MILP 调度
7. 独立结果验算与图表输出

运行代码时请将工作目录切换到项目根目录。原始附件保留在 `data/raw`，生成结果统一写入 `outputs`。

