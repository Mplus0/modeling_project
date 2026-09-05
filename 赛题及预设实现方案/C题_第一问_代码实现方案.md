# C题《面向算电协同的多目标调度优化研究》
## 第一问代码实现方案（基于当前建模稿）

> 文档定位：给代码手使用的“实现蓝图”。  
> 当前阶段只规定代码结构、数据流、数学模型到程序的映射、求解流程和结果输出，不展开具体 Python 实现。  
> 建模依据：当前《第一问.docx》建模方案与赛题附件数据。

---

## 1. 第一问总体任务

当前第一问分为两个**相对独立**的子任务：

1. **GPU 需求预测**
   - 根据历史任务到达记录构造 6 个区域 × 3 类任务 = 18 条小时级 GPU 需求序列；
   - 使用 0–2351 小时作为训练历史；
   - 使用 2352–2375 小时作为验证集选择预测模型参数；
   - 最终预测 2376–2399 小时 GPU 新增需求；
   - 使用 WAPE、MAE、RMSE 评价预测性能。

2. **基础算力调度**
   - 调度对象不是预测结果；
   - 使用 2376–2399 小时**实际到达的任务**；
   - 为每个任务确定：
     - 执行区域 `TargetRegion`
     - 开始时刻 `StartHour`
   - 满足网络时延、任务完成时限、GPU 容量、IT 功率、设施功率和 2406 小时终端约束；
   - 采用两阶段优化：
     1. 最小化归一化任务等待率；
     2. 在第一阶段服务质量基本不下降的前提下，最小化全局峰值 GPU 利用率。

整体流程：

```text
原始任务数据
│
├── A. GPU需求预测
│   ├── 构造18条小时级需求序列
│   ├── 训练/验证
│   ├── 参数选择
│   ├── 预测2376–2399
│   └── 预测误差评价
│
└── B. 基础算力调度
    ├── 读取2376–2399实际到达任务
    ├── 构造任务可行调度域
    ├── 第一阶段：最小化等待
    ├── 第二阶段：最小化峰值GPU利用率
    ├── 独立验算全部约束
    └── 输出调度表、逐时资源表与图表
```

---

# 2. 推荐技术栈

## 2.1 Python 环境

建议：

```text
Python >= 3.11
pandas
numpy
openpyxl
matplotlib
scipy（可选）
gurobipy（优先）
```

优化器优先级建议：

1. **Gurobi / gurobipy**
   - 适合当前二元整数规划；
   - 支持两阶段重复求解；
   - 支持 MIPGap、TimeLimit、Warm Start；
   - 比较适合后续第二问、第四问扩展。

2. 若没有 Gurobi：
   - HiGHS / Pyomo
   - PuLP

第一问目前 2376–2399 小时实际有约 **538 个任务**，其中：
- AITraining：194
- BatchInference：184
- RealTimeInference：160

通过提前构造可行域后，MILP 规模应明显小于直接建立 `任务 × 6区域 × 全部时刻` 的笛卡尔积变量。

---

# 3. 推荐项目目录

建议从第一问开始就建立可扩展项目，而不是把全部内容写在一个 Notebook 中。

```text
modeling_project/
│
├── data/
│   └── raw/
│       ├── workload_trace.xlsx
│       ├── GPU_information.xlsx
│       ├── network_latency.xlsx
│       ├── power_mapping.xlsx
│       ├── region_time_data.xlsx
│       └── storage_information.xlsx
│
├── src/
│   ├── config.py
│   ├── data_loader.py
│   ├── data_validator.py
│   ├── demand_builder.py
│   ├── forecast.py
│   ├── feasible_domain.py
│   ├── overlap.py
│   ├── scheduler_stage1.py
│   ├── scheduler_stage2.py
│   ├── result_validator.py
│   ├── metrics.py
│   └── visualization.py
│
├── scripts/
│   ├── 01_check_data.py
│   ├── 02_build_demand.py
│   ├── 03_run_forecast.py
│   ├── 04_run_schedule.py
│   └── 05_generate_report_outputs.py
│
├── outputs/
│   ├── forecast/
│   ├── schedule/
│   ├── metrics/
│   ├── figures/
│   └── logs/
│
├── notebooks/
│   └── exploration.ipynb
│
├── requirements.txt
├── README.md
└── main.py
```

### 原则

- `src/`：只放可复用函数和模型；
- `scripts/`：负责按顺序运行；
- `notebooks/`：只用于探索，不作为最终结果唯一来源；
- `outputs/`：所有论文需要的数据和图片必须自动导出。

---

# 4. 第一问实际使用的数据文件

## 4.1 workload_trace.xlsx

核心任务数据。

主要字段：

| 字段 | 程序含义 |
|---|---|
| `TaskID` | 任务唯一编号 |
| `TaskType` | AITraining / BatchInference / RealTimeInference |
| `ArrivalHour` | 到达时刻 |
| `GPU_Demand` | 任务运行时持续占用的等效 GPU |
| `EstimatedDuration_min` | 持续分钟数 |
| `DelaySensitivity` | 延迟敏感性 |
| `SourceRegion` | 来源区域 |
| `MaxLatency_ms` | 最大允许网络时延 |
| `LatestFinishHour` | 最晚完成时刻 |
| `EarliestStartHour` | 最早开始时刻 |
| `ExecutionMode` | 当前为 NonPreemptive |

程序新增派生字段：

```text
DurationHour = EstimatedDuration_min / 60
MaxDelayHour = LatestFinishHour - ArrivalHour - DurationHour
```

---

## 4.2 GPU_information.xlsx

主要使用：

| 字段 | 用途 |
|---|---|
| `Region` | 区域索引 |
| `Available_GPU` | GPU 容量硬约束 |
| `Max_IT_Power_MW` | IT 功率上限 |
| `PUE` | IT 功率 → 设施功率 |
| `Max_Facility_Power_MW` | 设施侧功率上限 |

注意：

> 第一问容量约束应使用 `Available_GPU`，不是 `Total_GPU`。

---

## 4.3 network_latency.xlsx

使用：

```text
FromRegion
ToRegion
NetworkLatency_ms
```

构造映射：

```python
latency[(source_region, target_region)] -> ms
```

并用于提前剔除：

```text
NetworkLatency_ms > MaxLatency_ms
```

的目标区域。

---

## 4.4 power_mapping.xlsx

三类任务单位 GPU IT 功率：

```text
AITraining           0.16 MW / EquivalentGPU
BatchInference       0.10 MW / EquivalentGPU
RealTimeInference    0.08 MW / EquivalentGPU
```

构造：

```python
gpu_power[task_type]
```

---

## 4.5 region_time_data.xlsx

第一问主要使用：

```text
Hour
Region
NonAI_IT_Load_MW
```

附件实际包含：

```text
Hour = 0 ... 2406
```

其中：

```text
0–2399      Main_0_2399
2400–2406   Closure_2400_2406
```

这对第一问尾部任务功率约束非常重要。

---

## 4.6 storage_information.xlsx

**第一问暂不进入当前模型。**

保留数据加载接口即可，为第三问、第四问使用。

---

# 5. 配置文件设计

建议将所有时间边界放在 `config.py`，禁止散落魔法数字。

```text
REGIONS = RegionA ... RegionF

TASK_TYPES =
    RealTimeInference
    BatchInference
    AITraining

TRAIN_START = 0
TRAIN_END = 2351

VALID_START = 2352
VALID_END = 2375

FORECAST_START = 2376
FORECAST_END = 2399

SCHEDULE_ARRIVAL_START = 2376
SCHEDULE_ARRIVAL_END = 2399

TERMINAL_TIME = 2406
```

### 调度资源检查时间范围

建议实现为：

```text
RESOURCE_HOURS = 2376 ... 2405
```

原因：

- 2376–2399 到达的任务可能运行到 2405；
- 当前模型要求所有任务在 2406 之前完成；
- GPU / IT / 设施功率约束不能只检查到 2399。

论文主评价指标仍按当前建模稿统计：

```text
2376 ... 2399
```

而：

```text
2400 ... 2405
```

作为尾部任务合法性和收尾结果检查。

---

# 6. 模块一：数据读取与一致性检查

## 6.1 `data_loader.py`

建议统一返回：

```text
tasks_df
gpu_info_df
latency_df
power_map_df
region_time_df
storage_df
```

并进一步生成字典：

```python
available_gpu[r]
max_it_power[r]
pue[r]
max_facility_power[r]

latency[q, r]

gpu_power[k]

non_ai_load[r, t]
```

---

## 6.2 `data_validator.py`

正式建模前必须自动检查：

### 任务表

```text
TaskID 是否唯一
ArrivalHour 是否位于 0–2399
GPU_Demand 是否 > 0
EstimatedDuration_min 是否 > 0
TaskType 是否属于三类任务
SourceRegion 是否属于六个区域
LatestFinishHour >= ArrivalHour
EarliestStartHour <= LatestFinishHour
ExecutionMode 是否为 NonPreemptive
```

### 区域数据

检查：

```text
6 个 Region 是否完整
Available_GPU > 0
PUE > 0
Max_IT_Power_MW > 0
Max_Facility_Power_MW > 0
```

### 网络时延

检查是否具有完整：

```text
6 × 6 = 36
```

个来源—目标组合。

### region_time_data

第一问至少检查：

```text
Region × Hour = 6 × 2407
```

是否齐全。

---

# 7. 模块二：GPU 需求序列构造

文件：

```text
demand_builder.py
```

当前建模中的预测对象是：

> 任务**到达时产生的原始新增 GPU 需求**，不是调度后的 GPU 利用率。

对于区域 $r$、任务类型 $k$、时刻 $t$：

$$
Y_{rkt}
=
\sum_{i:
a_i=t,\,
q_i=r,\,
k_i=k}
g_i
$$

其中：

- $a_i$：ArrivalHour
- $q_i$：SourceRegion
- $k_i$：TaskType
- $g_i$：GPU_Demand

程序实现结果建议采用长表：

```text
Hour
Region
TaskType
GPU_Demand
```

规模：

```text
2400 × 6 × 3 = 43200 rows
```

即使某一组合没有任务，也必须补：

```text
GPU_Demand = 0
```

不能缺行。

同时生成：

### 区域总需求

$$
Y_{rt}=\sum_kY_{rkt}
$$

### 系统总需求

$$
Y_t=\sum_r\sum_kY_{rkt}
$$

---

# 8. 模块三：GPU 需求统计分析

建议输出：

```text
outputs/forecast/demand_series.csv
outputs/metrics/demand_statistics.csv
```

统计维度：

```text
Region
TaskType
Region × TaskType
Hour
```

建议至少计算：

```text
count
mean
std
min
median
max
sum
zero_ratio
```

可生成：

1. 各 Region 总 GPU 新增需求曲线；
2. 三类 TaskType 总需求曲线；
3. Region × TaskType 平均需求热力图；
4. 18 条序列的均值 / 标准差 / 峰值表。

这部分服务于题目“统计分析”和论文数据特征描述。

---

# 9. 模块四：多时间尺度 GPU 需求预测

文件：

```text
forecast.py
```

---

## 9.1 当前模型

对每个 $(r,k)$：

### 长期平均

$$
L_{rk}
=
\frac{1}{T}
\sum_{\tau=0}^{T-1}Y_{rk\tau}
$$

### 最近 24 小时平均

$$
S_{rk}
=
\frac{1}{24}
\sum_{\tau=T-24}^{T-1}Y_{rk\tau}
$$

### 过去 7 天同小时平均

$$
D_{rkt}
=
\frac{1}{7}
\sum_{j=1}^{7}Y_{rk,t-24j}
$$

### 最终预测

$$
\hat Y_{rkt}
=
\alpha L_{rk}
+
\beta S_{rk}
+
\gamma D_{rkt}
$$

满足：

$$
\alpha+\beta+\gamma=1
$$

$$
\alpha,\beta,\gamma\ge 0
$$

---

# 10. 预测训练/验证流程

## 10.1 数据分段

```text
训练历史：
0–2351

验证：
2352–2375

最终预测：
2376–2399
```

---

## 10.2 参数选择

主要评价：

$$
WAPE=
\frac{
\sum_{r,k,t}|Y_{rkt}-\hat Y_{rkt}|
}{
\sum_{r,k,t}Y_{rkt}
}
$$

辅助：

$$
MAE=
\frac1N\sum|Y-\hat Y|
$$

$$
RMSE=
\sqrt{
\frac1N\sum(Y-\hat Y)^2
}
$$

程序结构建议：

```text
for candidate alpha:
    for candidate beta:
        gamma = 1 - alpha - beta

        if gamma < 0:
            continue

        使用0–2351构造预测输入
        预测2352–2375
        计算WAPE

选择WAPE最小的参数
```

---

## 10.3 当前建模稿尚未明确的实现参数

以下内容**不要由代码手永久写死**，先做配置项：

```text
alpha/beta/gamma 的搜索步长
验证阶段是否滚动更新历史
预测区间如何构造
风险裕度如何加入
```

尤其建模稿中提到“预测区间和风险裕度”，但当前正文没有给出具体公式。

因此当前第一版程序建议：

> 先完成点预测主模型；预测区间模块保留接口，待建模手给出具体定义后补充。

---

# 11. 预测输出格式

输出：

```text
outputs/forecast/forecast_2376_2399.csv
```

字段：

```text
Hour
Region
TaskType
Actual_GPU
Predicted_GPU
AbsoluteError
```

参数文件：

```text
outputs/forecast/forecast_parameters.json
```

例如：

```text
alpha
beta
gamma
validation_WAPE
validation_MAE
validation_RMSE
```

最终指标：

```text
outputs/metrics/forecast_metrics.csv
```

包含：

```text
overall
by_region
by_task_type
by_region_task_type
```

---

# 12. 模块五：调度任务提取

调度对象：

```text
ArrivalHour ∈ [2376, 2399]
```

当前附件中共有约：

```text
538 个任务
```

注意：

> 不使用预测结果生成任务。

预测模块和调度模块只在论文层面属于同一问，在程序输入层面彼此独立。

---

# 13. 模块六：任务可行调度域构造

文件：

```text
feasible_domain.py
```

这是 MILP 性能最重要的预处理步骤。

对于任务 $i$：

```text
来源区域       q_i
到达时间       a_i
持续时间       d_i
最晚完成时间   F_i
最大时延       L_i^max
```

目标区域 $r$，开始时间 $s$。

必须满足：

$$
L_{q_i,r}\le L_i^{max}
$$

$$
s\ge a_i
$$

$$
s+d_i\le F_i
$$

并满足：

$$
s+d_i\le 2406
$$

---

## 13.1 开始时刻

当前模型假设：

> 开始时刻只允许整点。

因此：

```text
s ∈ integers
```

对于普通可延迟任务：

```text
s = ArrivalHour ... floor(min(LatestFinishHour, 2406) - DurationHour)
```

---

## 13.2 实时推理任务

对于：

```text
TaskType == RealTimeInference
```

强制：

$$
s=a_i
$$

所以实时任务只需要选择：

```text
TargetRegion
```

不需要枚举多个开始时刻。

---

## 13.3 可行域数据结构

不要建立：

```text
all_tasks × all_regions × all_hours
```

的完整变量矩阵。

建议：

```python
feasible_options[i] = [
    (r1, s1),
    (r1, s2),
    (r2, s1),
    ...
]
```

只为：

```text
(r, s) ∈ Ω_i
```

建立二元变量。

这是后续问题扩展时必须坚持的稀疏建模方式。

---

## 13.4 建模前必须检查

```text
len(feasible_options[i]) > 0
```

如果某任务可行域为空：

```text
立即报错
输出 TaskID
输出导致不可行的原因
不要直接进入优化器
```

---

# 14. 模块七：非整数持续时间 Overlap

文件：

```text
overlap.py
```

任务持续时间：

$$
d_i=\frac{D_i}{60}
$$

任务从 $s$ 时刻开始，与小时区间：

$$
[t,t+1)
$$

的重叠长度：

$$
\phi_{ist}
=
\max
\left(
0,
\min(s+d_i,t+1)-\max(s,t)
\right)
$$

满足：

$$
0\le\phi_{ist}\le1
$$

---

## 14.1 示例

任务：

```text
StartHour = 2380
Duration = 90 min = 1.5 h
GPU = 100
```

则：

```text
Hour 2380:
Overlap = 1

Hour 2381:
Overlap = 0.5

其他小时:
Overlap = 0
```

GPU 占用贡献：

```text
2380 -> 100 × 1.0
2381 -> 100 × 0.5
```

---

## 14.2 推荐预计算

优化前预先构造：

```python
overlap[(i, s, t)]
```

但只保存：

```text
overlap > 0
```

的项。

进一步建议建立反向索引：

```python
active_options[(r, t)]
```

表示：

> 哪些 `(i, r, s)` 决策会占用 Region r 的时刻 t。

这样构造 GPU / Power 约束时不需要遍历全部变量。

---

# 15. 模块八：MILP 决策变量

对于：

$$
(r,s)\in\Omega_i
$$

定义：

$$
x_{irs}\in\{0,1\}
$$

含义：

```text
x[i,r,s] = 1
```

表示：

> 任务 i 在区域 r，于 s 时刻开始执行。

每个任务：

$$
\sum_{(r,s)\in\Omega_i}x_{irs}=1
$$

这一变量同时确定：

```text
执行区域
开始时刻
```

因此天然保证：

- 不拆分；
- 单区域运行；
- 不中途迁移。

---

# 16. 模块九：GPU 容量约束

时刻 $t$，区域 $r$：

$$
G_{rt}
=
\sum_{i,s}
g_i\phi_{ist}x_{irs}
$$

满足：

$$
G_{rt}\le A_r
$$

其中：

```text
A_r = Available_GPU
```

GPU 利用率：

$$
U_{rt}
=
\frac{G_{rt}}{A_r}
$$

### 实现时间范围

建议对：

```text
t = 2376 ... 2405
```

全部建立资源约束。

---

# 17. 模块十：IT 功率约束

单位 GPU 功率：

$$
p_k
$$

AI IT 功率：

$$
P^{AI}_{rt}
=
\sum_{i,s}
p_{k_i}g_i\phi_{ist}x_{irs}
$$

非 AI 固定负荷：

$$
P^{NonAI}_{rt}
$$

来自：

```text
region_time_data.xlsx
NonAI_IT_Load_MW
```

总 IT 功率：

$$
P^{IT}_{rt}
=
P^{NonAI}_{rt}
+
P^{AI}_{rt}
$$

满足：

$$
P^{IT}_{rt}
\le
P_r^{IT,max}
$$

---

# 18. 模块十一：设施功率约束

设施侧功率：

$$
P^{Fac}_{rt}
=
PUE_r
\cdot
P^{IT}_{rt}
$$

满足：

$$
PUE_r
\cdot
P^{IT}_{rt}
\le
P_r^{Fac,max}
$$

注意：

> GPU 还有剩余容量，并不代表任务一定可以放入该 Region；还必须同时通过 IT 和设施功率约束。

---

# 19. 模块十二：终端约束

当前建模要求：

$$
s+d_i\le2406
$$

程序必须在两个位置检查：

1. 构造可行域时提前剔除；
2. 求解结束后独立再次验算。

---

# 20. 模块十三：第一阶段优化——最小化任务等待

文件：

```text
scheduler_stage1.py
```

任务等待：

$$
T_i^{wait}=s-a_i
$$

任务最大可延迟时间：

$$
H_i=F_i-a_i-d_i
$$

归一化等待率：

$$
\eta_i=
\frac{s-a_i}{H_i+\varepsilon}
$$

第一阶段：

$$
\min J_1
=
\sum_i
\sum_{(r,s)\in\Omega_i}
\frac{s-a_i}{H_i+\varepsilon}
x_{irs}
$$

---

## 20.1 实现注意

当前建模稿中：

```text
epsilon = 极小正数
```

但没有给具体值。

因此：

```text
EPSILON
```

必须放在配置文件中，而不是散落在代码里。

---

## 20.2 第一阶段输出

至少保存：

```text
J1_star
solver_status
runtime
MIPGap
```

以及第一阶段完整解。

---

# 21. 模块十四：第二阶段优化——最小化峰值 GPU 利用率

文件：

```text
scheduler_stage2.py
```

在第二阶段重新建立/复用模型。

加入：

$$
J_1
\le
(1+\delta)J_1^*
$$

新增连续变量：

$$
U_{max}\ge0
$$

并满足：

$$
\frac{G_{rt}}{A_r}\le U_{max}
$$

对所有相关：

```text
Region r
Hour t
```

成立。

第二阶段目标：

$$
\min U_{max}
$$

---

## 21.1 当前待确认参数

```text
delta
```

建模稿没有给具体数值。

必须作为配置项：

```python
SERVICE_DEGRADATION_DELTA = ...
```

由建模手最终确定。

---

## 21.2 推荐求解方式

第一阶段得到解后：

```text
Stage 1 Solution
```

可作为第二阶段：

```text
Warm Start
```

提高求解效率。

---

# 22. 调度主程序完整流程

建议：

```text
run_schedule()
│
├── 1. load_data()
├── 2. validate_data()
├── 3. select tasks with ArrivalHour 2376–2399
├── 4. derive DurationHour / MaxDelayHour
├── 5. build_feasible_domains()
├── 6. check every task has feasible options
├── 7. precompute_overlap()
├── 8. build_stage1_model()
├── 9. solve_stage1()
├──10. save J1*
├──11. build/update_stage2_model()
├──12. add J1 <= (1+delta)J1*
├──13. add Umax constraints
├──14. solve_stage2()
├──15. decode x[i,r,s]
├──16. independently validate solution
├──17. calculate metrics
└──18. export tables and figures
```

---

# 23. 调度结果解码

根据：

```text
x[i,r,s] = 1
```

得到每个任务：

```text
TaskID
TaskType
SourceRegion
TargetRegion
ArrivalHour
StartHour
DurationHour
FinishHour
GPU_Demand
MaxLatency_ms
ActualLatency_ms
WaitHour
LatestFinishHour
```

其中：

$$
FinishHour=StartHour+DurationHour
$$

$$
WaitHour=StartHour-ArrivalHour
$$

---

# 24. 独立结果验算模块

文件：

```text
result_validator.py
```

**验算必须独立于优化模型。**

不能只依赖：

```text
solver_status == OPTIMAL
```

---

## 24.1 任务级检查

每个任务检查：

### 唯一调度

```text
每个 TaskID 恰好出现一次
```

### 到达时间

$$
StartHour\ge ArrivalHour
$$

### 实时任务

若：

```text
RealTimeInference
```

则：

$$
StartHour=ArrivalHour
$$

### SLA

$$
Latency(SourceRegion,TargetRegion)
\le
MaxLatency
$$

### Deadline

$$
FinishHour
\le
LatestFinishHour
$$

### 终端

$$
FinishHour
\le
2406
$$

---

## 24.2 Region × Hour 级检查

重新根据最终任务表计算：

```text
GPU_Used
AI_IT_Power
Total_IT_Power
Facility_Power
```

检查：

$$
GPUUsed_{rt}\le AvailableGPU_r
$$

$$
ITPower_{rt}\le MaxITPower_r
$$

$$
FacilityPower_{rt}\le MaxFacilityPower_r
$$

---

## 24.3 最终验算摘要

程序建议打印并导出：

```text
Total tasks
Scheduled tasks
Finish rate
SLA violations
Deadline violations
Terminal violations
GPU overload count
IT power overload count
Facility power overload count
```

理想结果：

```text
Finish Rate                 = 100%
SLA Violations              = 0
Deadline Violations         = 0
Terminal Violations         = 0
GPU Overload                = 0
IT Power Violations         = 0
Facility Power Violations   = 0
```

---

# 25. 调度评价指标

当前建模稿要求：

## 25.1 区域平均 GPU 利用率

$$
\bar U_r
=
\frac1{24}
\sum_{t=2376}^{2399}
U_{rt}
$$

---

## 25.2 区域峰值 GPU 利用率

$$
U_r^{max}
=
\max_{2376\le t\le2399}U_{rt}
$$

---

## 25.3 平均等待时间

$$
\bar T^{wait}
=
\frac1N
\sum_i(s_i-a_i)
$$

建议同时按 TaskType 计算：

```text
RealTimeInference
BatchInference
AITraining
```

---

## 25.4 按时完成率

$$
R_{finish}
=
\frac{N_{finish}}{N}
$$

---

## 25.5 建议额外输出

虽然当前模型正文未全部要求，但代码层建议同时保存：

```text
global_peak_gpu_utilization
mean_gpu_utilization
p95_gpu_utilization
mean_wait_by_task_type
max_wait_by_task_type
task_migration_rate
migration_rate_by_task_type
region_inflow_count
region_outflow_count
```

这些指标可以帮助论文手解释模型结果，但是否写入正式论文由建模手/论文手决定。

---

# 26. 逐时资源结果表

建议：

```text
outputs/schedule/region_hour_resource.csv
```

字段：

```text
Hour
Region
GPU_Used
Available_GPU
GPU_Utilization
AI_IT_Power_MW
NonAI_IT_Power_MW
Total_IT_Power_MW
Max_IT_Power_MW
Facility_Power_MW
Max_Facility_Power_MW
```

时间范围建议：

```text
2376–2405
```

论文主图可以只截：

```text
2376–2399
```

但尾部数据必须保留用于合法性检查。

---

# 27. 图表输出方案

第一问建议自动生成：

## 27.1 预测部分

```text
01_system_gpu_demand_actual_vs_predicted.png
02_region_forecast_comparison.png
03_tasktype_forecast_comparison.png
04_forecast_error_by_region.png
```

---

## 27.2 调度部分

### 必做

```text
05_task_gantt.png
06_gpu_utilization_by_region.png
```

对应当前建模稿要求：

- 任务甘特图；
- 区域 GPU 利用率曲线。

### 建议增加

```text
07_gpu_utilization_heatmap.png
08_task_migration_matrix.png
09_wait_time_distribution.png
10_region_power_utilization.png
```

---

# 28. 推荐最终输出目录

```text
outputs/
│
├── forecast/
│   ├── demand_series.csv
│   ├── forecast_2376_2399.csv
│   └── forecast_parameters.json
│
├── schedule/
│   ├── task_schedule.csv
│   ├── region_hour_resource.csv
│   ├── stage1_solution.csv
│   └── stage2_solution.csv
│
├── metrics/
│   ├── demand_statistics.csv
│   ├── forecast_metrics.csv
│   ├── schedule_metrics.csv
│   └── validation_report.txt
│
├── figures/
│   ├── ...
│
└── logs/
    ├── stage1_solver.log
    └── stage2_solver.log
```

---

# 29. 代码实现顺序

正式编码时不要一开始就写优化器。

建议严格按照以下顺序：

## Step 1：读取数据

目标：

```text
所有附件可以稳定读取
字段名完全确认
```

---

## Step 2：数据验证

目标：

```text
确认原始数据合法
```

---

## Step 3：构造 18 条 GPU 需求序列

目标：

```text
43200 行完整 Region × TaskType × Hour 表
```

---

## Step 4：完成统计分析

先确认：

```text
需求量级合理
任务分布合理
没有聚合错误
```

---

## Step 5：完成预测模型

先跑：

```text
2352–2375 validation
```

确认指标，再：

```text
2376–2399 final forecast
```

---

## Step 6：只实现可行域

暂时不写 MILP。

随机抽取几个任务人工核对：

```text
哪些 Region 可去
哪些 StartHour 可选
```

---

## Step 7：实现 Overlap

用人工例子验证：

```text
60 min
90 min
150 min
399 min
```

---

## Step 8：建立最小 MILP

先只加入：

```text
任务唯一选择
GPU容量
```

用少量任务测试。

---

## Step 9：逐步加入约束

依次加入：

```text
网络时延（已在可行域处理）
Deadline
IT Power
Facility Power
Terminal
```

每加入一组，都运行小规模测试。

---

## Step 10：实现第一阶段

```text
min J1
```

确认能够求出可行最优解。

---

## Step 11：实现第二阶段

加入：

```text
J1 <= (1+delta)J1*
Umax
```

并求：

```text
min Umax
```

---

## Step 12：独立验算

只有：

```text
所有 violation = 0
```

才能进入正式结果输出。

---

## Step 13：自动生成论文结果

输出：

```text
CSV
JSON
PNG
TXT
```

使论文手完全不需要打开优化代码。

---

# 30. 小规模单元测试建议

正式跑 538 个任务之前，先人工构造 5–20 个任务进行测试。

至少覆盖：

### Case A：实时任务

```text
StartHour 必须等于 ArrivalHour
```

### Case B：时延不可行

```text
RegionA -> RegionD latency > MaxLatency
```

确认 RegionD 不生成变量。

### Case C：90 分钟任务

确认：

```text
Overlap = 1 + 0.5
```

### Case D：GPU 容量刚好达到上限

确认：

```text
<= 允许
> 不允许
```

### Case E：GPU 未满但功率超限

确认模型仍然禁止该调度。

### Case F：尾部任务

任务在：

```text
2399 到达
```

运行到：

```text
2400–2405
```

确认仍然参与资源约束。

### Case G：2406 超时

确认直接从可行域中剔除。

---

# 31. 建议的日志输出

每次正式运行建议记录：

```text
数据读取完成
任务总数
预测序列数
调度任务数
平均可行域大小
最大可行域大小
总二元变量数
GPU约束数
IT功率约束数
设施功率约束数
Stage1 Status
Stage1 J1*
Stage1 Runtime
Stage2 Status
Stage2 Umax
Stage2 Runtime
MIPGap
Validation Summary
```

这样比赛期间模型无解或结果异常时容易定位。

---

# 32. 当前模型中需要建模手确认的参数

以下项目当前建模文档没有给出完整数值/口径，代码设计应保留配置项。

## 32.1 预测参数搜索粒度

需要确定：

```text
alpha / beta / gamma
```

搜索步长。

例如是否：

```text
0.01
0.02
0.05
```

当前文档未指定。

---

## 32.2 验证方式

2352–2375 的预测究竟：

### 方案 A

一次性使用 0–2351：

```text
预测完整未来24小时
```

还是：

### 方案 B

逐小时滚动：

```text
预测2352
观察2352真实值
更新历史
预测2353
...
```

当前文档需要进一步明确。

---

## 32.3 epsilon

$$
\varepsilon
$$

当前只写：

> 极小正数

需要明确具体值。

---

## 32.4 delta

$$
\delta
$$

第二阶段允许第一阶段目标恶化多少，需要建模手给出。

---

## 32.5 预测区间与风险裕度

建模假设中提及，但正文暂未给出数学表达式。

第一版程序不要自行杜撰。

---

## 32.6 第二阶段 Umax 的统计时间范围

当前结果评价明确写：

```text
2376–2399
```

但尾部任务可以运行至 2405。

代码建议：

- 资源约束：2376–2405；
- 论文主评价：2376–2399。

若第二阶段的 `Umax` 是否也只针对 2376–2399，需要最终由建模手确认。

---

# 33. 性能优化原则

即使第一问规模不大，也从一开始遵守以下原则。

## 33.1 稀疏变量

只建立：

```text
x[i,r,s] for (r,s) ∈ Ω_i
```

---

## 33.2 提前筛选区域

先用：

```text
NetworkLatency
```

删除不可行 Region。

---

## 33.3 提前筛选时间

只枚举：

```text
ArrivalHour <= StartHour <= LatestFinish - Duration
```

---

## 33.4 Overlap 只存非零项

避免：

```text
task × start × all_hours
```

完整矩阵。

---

## 33.5 建立 Region-Hour 反向索引

便于快速生成：

```text
GPU
Power
Facility
```

约束。

---

## 33.6 第二阶段复用第一阶段解

使用 Warm Start。

---

# 34. 与后续问题的代码兼容设计

第一问建议把以下模块做成公共层：

```text
data_loader
data_validator
task preprocessing
feasible_domain
overlap
GPU accounting
AI power accounting
PUE accounting
result_validator
visualization
```

后续：

### 第二问

在第一问基础上增加：

```text
电价
碳排放
新能源
购电
售电
```

### 第三问

增加：

```text
SOC
Charge
Discharge
```

### 第四问

将：

```text
任务调度
+
电网
+
新能源
+
储能
```

联合求解。

因此第一问不应写成一次性脚本。

---

# 35. 第一问最终验收标准

代码手交付第一问前，应满足：

## 预测

- [ ] 成功生成 18 条完整需求序列
- [ ] 完成 0–2351 历史建模
- [ ] 完成 2352–2375 参数验证
- [ ] 完成 2376–2399 预测
- [ ] 输出 WAPE
- [ ] 输出 MAE
- [ ] 输出 RMSE
- [ ] 输出预测结果表
- [ ] 输出预测图

## 调度

- [ ] 正确提取 2376–2399 实际到达任务
- [ ] 所有任务具有非空可行域
- [ ] 实时任务到达即开工
- [ ] 所有任务只选择一个 Region / StartHour
- [ ] 网络时延全部合法
- [ ] Deadline 全部合法
- [ ] GPU 无超载
- [ ] IT Power 无超载
- [ ] Facility Power 无超载
- [ ] 全部任务最晚于 2406 完成
- [ ] Stage 1 成功求解
- [ ] Stage 2 成功求解
- [ ] 独立验算全部通过
- [ ] 完成率 100%
- [ ] 输出任务调度表
- [ ] 输出 Region-Hour 资源表
- [ ] 输出甘特图
- [ ] 输出 GPU 利用率曲线

---

# 36. 推荐的第一版开发里程碑

## Milestone 1：数据层

完成：

```text
data_loader
data_validator
```

验收：

> 可以稳定读取全部附件，并打印正确的数据规模和字段。

---

## Milestone 2：预测层

完成：

```text
demand_builder
forecast
forecast_metrics
```

验收：

> 可以自动生成 2376–2399 的预测结果和误差指标。

---

## Milestone 3：调度预处理

完成：

```text
task selection
feasible domain
overlap
```

验收：

> 任意抽取 TaskID，可以打印其所有合法 `(Region, StartHour)`。

---

## Milestone 4：Stage 1

完成：

```text
MILP constraints
min J1
```

验收：

> 得到完整可行调度，所有硬约束通过。

---

## Milestone 5：Stage 2

完成：

```text
service constraint
min Umax
```

验收：

> 服务质量基本保持，同时峰值 GPU 利用率得到优化。

---

## Milestone 6：结果层

完成：

```text
validator
metrics
figures
exports
```

验收：

> 一条命令可以重新生成第一问所有论文数据和图片。

---

# 37. 最终推荐主入口

最终建议可以通过：

```bash
python main.py --question 1
```

或：

```bash
python scripts/01_check_data.py
python scripts/02_build_demand.py
python scripts/03_run_forecast.py
python scripts/04_run_schedule.py
python scripts/05_generate_report_outputs.py
```

完整复现第一问。

比赛最终提交前应保证：

> 从原始附件开始，在一个干净环境中可以重新运行并得到相同的核心结果。

---

# 38. 当前阶段代码手下一步

当前还不需要直接写完整优化代码。

推荐下一步依次完成：

1. 建立项目目录；
2. 写数据读取层；
3. 对 6 个 Excel 文件做字段与数据范围检查；
4. 构造 18 条 GPU 需求序列；
5. 和建模手确认：
   - 参数搜索粒度；
   - 验证是否滚动；
   - $\varepsilon$；
   - $\delta$；
   - 预测区间/风险裕度；
   - 第二阶段 $U_{max}$ 时间范围；
6. 再正式开始预测和 MILP 编码。

---

## 结论

当前第一问适合采用：

```text
Pandas/Numpy 数据处理
+
多时间尺度加权预测
+
稀疏 MILP 调度
+
两阶段优化
+
独立约束验算
+
自动化表格/图形输出
```

作为代码手，核心不是简单“把公式写成 Python”，而是确保：

```text
模型可计算
→ 求解可复现
→ 约束无违反
→ 指标可解释
→ 论文结果可直接使用
```

这份代码架构也应作为后续问题二、三、四的公共基础。
