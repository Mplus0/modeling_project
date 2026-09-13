# 2026 全国大学生数学建模竞赛 C 题项目

本仓库用于 2026 全国大学生数学建模竞赛 C 题“微网与外部电网电力调控策略”的建模、编程、实验、结果整理与团队协作。

当前项目已完成赛题资料归档、只读数据审计、标准化预处理和问题一两阶段线性规划。预处理已冻结；问题一完整调度、指标及按已确认 slot 行序填写的官方结果副本已输出。问题二动态预测与逐日优化、模板副本及论文表已实现，等待数值验收；尚未实现问题三、四。

## 项目结构

```text
modeling _project/
├── 赛题及预设实现方案/
│   ├── CUMCM2026Problems/
│   │   ├── A题/
│   │   │   ├── A题.pdf
│   │   │   └── 附件/
│   │   ├── B题/
│   │   │   ├── B题.pdf
│   │   │   └── 附件/
│   │   ├── C题/
│   │   │   ├── C题.pdf
│   │   │   └── 附件/
│   │   └── format2026.doc
│   ├── C题_初始分析与比赛计划.md
│   └── .gitkeep
├── data/
│   ├── raw/
│   │   ├── 附件1.xlsx
│   │   ├── 附件2.xlsx
│   │   ├── 附件3.xlsx
│   │   ├── 附件4.xlsx
│   │   └── 附件5/
│   │       ├── result1.xlsx
│   │       ├── result2.xlsx
│   │       ├── result3.xlsx
│   │       ├── result4-2.xlsx
│   │       └── result4-3.xlsx
│   └── processed/
│       ├── q1_input.csv
│       ├── historical_power.csv
│       ├── pv_forecast_hourly.csv
│       └── electricity_price.csv
├── src/
│   ├── common/                 # 加载、审计、时间解析和标准化预处理（已冻结）
│   └── q1/                     # optimizer.py、result_writer.py
├── scripts/                    # 01_check_data.py、02_preprocess.py、03_run_q1.py
├── tests/                      # 审计、预处理和 Q1 测试
├── outputs/
│   ├── data_quality/           # 审计报告和预处理摘要
│   ├── figures/
│   │   └── .gitkeep
│   ├── forecast/
│   │   └── .gitkeep
│   ├── logs/
│   │   └── .gitkeep
│   ├── metrics/
│   │   └── .gitkeep
│   ├── schedule/
│   │   └── .gitkeep
│   └── submissions/
│       └── .gitkeep
├── tmp/
├── .gitignore
├── LICENSE
├── README.md
└── requirement.txt
```

## 目录说明

| 路径 | 用途 |
| --- | --- |
| `赛题及预设实现方案/CUMCM2026Problems/` | 保存 A、B、C 三道正式赛题、对应附件及论文格式文件，作为原始资料归档。 |
| `赛题及预设实现方案/C题_初始分析与比赛计划.md` | 记录 C 题文件清单、问题拆解、初始建模方案、代码规划和比赛时间安排。 |
| `data/raw/` | 保存 C 题官方原始数据及结果模板。该目录中的文件原则上只读，不应直接覆盖。 |
| `data/processed/` | 保存清洗、转换、对齐或特征构造后的数据。所有内容应能由原始数据和代码重新生成。 |
| `src/` | 保存可复用的核心代码，包括数据处理、预测、优化、仿真、评价和结果导出模块。 |
| `scripts/` | 保存按流程执行的入口脚本，例如数据检查、预处理、模型求解和结果生成脚本。 |
| `outputs/figures/` | 保存论文使用的图表及可视化结果。 |
| `outputs/forecast/` | 保存负载、光伏等预测任务的结果和中间文件。 |
| `outputs/logs/` | 保存程序运行日志、求解器日志和异常记录。 |
| `outputs/metrics/` | 保存预测误差、成本、约束验证等评价指标。 |
| `outputs/schedule/` | 保存购电、储能充放电和滚动调整等调度结果。 |
| `outputs/submissions/` | 保存填写完成、经过检查并准备提交的结果文件副本。 |
| `tmp/` | 保存调试或计算过程中产生的临时文件，不存放唯一版本的重要成果。 |

`.gitkeep` 仅用于让 Git 保留尚未产生正式内容的目录。目录中加入文件后，可以保留或删除对应的 `.gitkeep`，不会影响项目运行。

## 赛题概述

C 题研究包含光伏发电、居民负载、储能设备和外部电网的微网系统。目标是在满足供电平衡、储能容量、充放电功率及相关交易规则的前提下，制定合理的购电与储能控制策略，尽可能降低总购电成本。

四个问题逐步引入更真实的决策条件：

1. 确定性单日购电与储能调度；
2. 光伏和负载预测误差下的计划购电与紧急购电；
3. 多时刻滚动预测下的购电调整、违约成本与紧急购电；
4. 实时波动电价下对问题 2、问题 3 的重新优化。

详细的题目拆解、输出要求和初始实现思路见 `赛题及预设实现方案/C题_初始分析与比赛计划.md`。

## 环境配置

建议使用 Python 3.11，并在独立的 Conda 环境中安装依赖：

```bash
conda create -n modeling_project python=3.11
conda activate modeling_project
python -m pip install -r requirement.txt
```

当前依赖包括：

- `pandas`、`numpy`：数据处理与数值计算；
- `openpyxl`：Excel 数据及结果模板读写；
- `matplotlib`：结果可视化；
- `scipy`、`scikit-learn`：科学计算、预测和模型评价；
- `pyscipopt`：基于 SCIP 的数学规划求解。

如比赛过程中新增第三方库，请同步更新 `requirement.txt`，确保所有成员可以复现运行环境。

## 建议工作流程

1. 以 `赛题及预设实现方案/CUMCM2026Problems/C题/` 中的题面和附件为官方依据。
2. 从 `data/raw/` 读取工作数据，不修改原始 Excel 文件及结果模板。
3. 将只读审计报告写入 `outputs/data_quality/`；后续经确认的清洗和格式转换结果才写入 `data/processed/`。
4. 在 `src/` 中实现可复用模块，在 `scripts/` 中编写编号清晰的运行入口。
5. 将预测、调度、指标、图表和日志分别写入 `outputs/` 下对应目录。
6. 填写结果模板时，先复制原始模板，再将完成的副本写入 `outputs/submissions/`。
7. 提交前统一检查模型约束、单位、时间索引、结果模板和论文数据是否一致。

## 项目约定

- 所有代码从项目根目录运行，代码中使用相对路径，不写个人电脑的绝对路径。
- 原始数据、处理后数据、模型输出和最终提交文件分开保存。
- 入口脚本建议按执行顺序编号，如 `01_check_data.py`、`02_preprocess.py`、`03_run_model.py`。
- 随机算法固定随机种子；关键实验记录参数、目标值、评价指标和运行时间。
- 图表和表格采用含义明确的文件名，并记录其对应的生成脚本。
- 正式提交文件生成后应进行独立校验，不以“程序成功运行”代替结果正确性检查。

## 注意事项

- 赛题、附件和比赛成果应严格按照竞赛规则管理；如使用远程仓库，应确认仓库权限和材料上传要求。
- `data/raw/附件5/` 中保存的是官方结果模板，请勿直接覆盖，以免丢失原始格式。
- `outputs/submissions/` 中的文件应是可追溯、可复现并通过检查的最终候选版本。
- Office 临时文件、Python 缓存和系统文件已在 `.gitignore` 中排除。

## 初始数据审计（Q1–Q4 共用）

从项目根目录运行，使用已有的 `pandas` 和 `openpyxl` 依赖：

```bash
conda run -n modeling_project python scripts/01_check_data.py
conda run -n modeling_project python -m unittest discover -s tests -v
```

可通过 `--raw-dir 路径` 指定另一份只读附件目录。默认递归检查 `data/raw/` 中的全部 9 个官方工作簿（包括附件 5 模板），跳过 Excel 锁文件。输出固定保存到 `outputs/data_quality/`，再次运行会更新报告，不写入原始附件或 `data/processed/`。旧版 `.xls` 会报告不支持，且返回失败，不自动转换。

| 模块 | 职责 |
| --- | --- |
| `src/common/data_loader.py` | 查找附件、计算 SHA-256、只读加载全部工作表，保留原始表头、公式文本和空白。 |
| `src/common/data_validator.py` | 逐列类型、缺失位置、重复行、原生数值 min/max/mean、负值、零值及公式统计。 |
| `src/common/time_utils.py` | 显式时间标签解析、重复时间戳、间隔分布、缺口、逐日记录数及预报发布/目标结构。 |
| `scripts/01_check_data.py` | 执行审计、记录单表错误、核对文件哈希并导出报告。 |
| `tests/test_data_audit.py` | 合成样本验证跨日、缺口、重复、预报空日期保留及原文件不变。 |

输出包括 `summary.md`（工作表概览、时间轴及待确认项）和 `audit.json`（完整统计、Excel 行列位置、缺失时间清单、逐日数量、预报结构和文件哈希）。有加载/审计错误或文件哈希变化时退出码为 1；数据质量待确认项本身不导致运行失败。

审计口径：第一行为表头，Excel 尺寸包括表头和已声明范围内的空白行列；重复行报告额外重复数及所有参与重复的 Excel 行号。缺失统计含空值、空字符串和纯空白字符串，原字符串不修改；文本 `NA` 和文本数字不自动转换。dtype 是 pandas 内存推断类型，另列原始 Python 类型计数。数值统计仅包含原生数值，非有限数单独计数，公式保留文本不求值。空白结果模板单独标识，照常统计。

时间检查使用明确标示的参考间隔：点序列 10 分钟、日期 1 天、预报发布 6 小时、预报步长 1 小时。缺口只比较可解析时间轴首尾内的参考网格，不推断边界外记录。`0:00+1`、`24:00` 按显式跨日标记解析；按源日期和自然日分别报告记录数。数值单元格空白不等同于时间标签缺失。没有日期的单日序列报告未注明日期的记录数。

初始审计中的 `TODO: 需建模手确认` 是审计阶段的暂定语义提示，涉及参考间隔及覆盖范围、缺失/重复/负值/零值的业务处理、区间标签索引端点和跨日后缀含义，不代表当前预处理仍有未决事项。只读审计不前向填充附件 3 的空白日期，因此仅对同一行显式日期与预报时刻构建发布时刻，未解析行另列；目标时间在当时仅报告“显式发布时刻 + 表头小时数”的候选结构。显式发布轴的缺口不代表预报数值行缺失。审计报告保留当时的检查口径，不填充、删除、插值、裁剪、归一化或覆盖官方数据。标准化预处理按下节已明确的规则执行，当前没有未解决的建模确认事项。

## 标准化数据预处理

从项目根目录使用 `modeling_project` Conda 环境运行，不需修改 shell 配置或安装新增依赖：

```bash
conda run --no-capture-output -n modeling_project python -X utf8 scripts/02_preprocess.py
conda run -n modeling_project python -m unittest discover -s tests -v
```

`src/common/preprocessing.py` 复用现有 `data_loader.py`、`data_validator.py`、`time_utils.py`，实现附件 1–4 的结构检查及标准化；`scripts/02_preprocess.py` 为入口；`tests/test_preprocessing.py` 包含官方数据集成验证和错误结构拒绝测试。输入固定为 `data/raw/附件1.xlsx` 至 `附件4.xlsx`，附件 5 只纳入原文件哈希检查，不加载或预处理模板。

运行命令的 `--no-capture-output` 和 `-X utf8` 用于避免 Windows 下 Conda 捕获中文日志的编码错误，只影响本次进程，不修改 shell 配置或全局环境变量。

| 输出（`data/processed/`） | 行数 | 列及口径 |
| --- | ---: | --- |
| `q1_input.csv` | 144 | `slot`（1..144）、`source_time`、`price_yuan_per_kwh`、`load_kw`、`pv_forecast_kw`、`load_kwh`、`pv_forecast_kwh`。保留官方时刻标签，不生成区间标签。 |
| `historical_power.csv` | 52560 | `datetime`、`source_date`、`source_time`、`load_kw`、`pv_actual_kw`、`load_kwh`、`pv_actual_kwh`。两张宽表时间标签逐位置验证一致后组合。 |
| `pv_forecast_hourly.csv` | 35040 | `issue_datetime`、`target_datetime`、`horizon_hour`、`pv_forecast_kw`。1460 个发布时刻，每次 24 个小时预报。 |
| `electricity_price.csv` | 52560 | `datetime`、`source_date`、`source_time`、`price_yuan_per_kwh`。电价保持原值，不乘 10 分钟换算系数。 |

CSV 使用 UTF-8，无额外索引列，日期时间采用 `YYYY-MM-DD HH:MM:SS`，源日期采用 `YYYY-MM-DD`。官方源时间字符串（包括 `0:00+1`）原样保留；Excel `time` 对象序列化为 `HH:MM:SS`。`0:00+1` 解释为源日期次日 00:00，保留最后一天对应的跨年终点。新增电量列均为相应功率乘以 `10/60` 小时；原始功率、电价和小时预报数值不改动。

附件 3 先验证全表为 365 个连续、唯一的四行日组：组首须有有效日期，时刻须依次为 00:00、06:00、12:00、18:00，组内显式日期须与组首一致。只有全部验证通过后，才为组内展示用空白日期推导日期，且不修改原始表或加载所得的 DataFrame。目标时间等于发布时刻加 `horizon_hour` 小时；发布/目标组合唯一，同一目标被多个发布时刻预报是允许的。不做小时到十分钟的重采样或插值。

输入尺寸、表头、数值缺失、非数值或非有限值、日期分组、时间连续性或表间对齐任一检查失败即停止并报错，不静默修复。所有输出验证通过后才写出四份 CSV；再次成功运行会替换这些派生文件。报告 `outputs/data_quality/preprocessing_summary.md` 记录输入/输出行数、分辨率、缺失状态、日期补全规则和数量，以及全部 9 个官方工作簿前后的 SHA-256。不会写入 `data/raw/`，不会删除样本、裁剪、归一化、训练模型或求解优化问题。

全套测试共 12 项（原审计 4 项、预处理 8 项），覆盖输出数量、CSV 数值往返、时间唯一性及跨日边界、10 分钟电量换算、每日发布结构和每次 24 条预报、错误结构拒绝、无意外缺失、原文件和模板哈希不变。上述标准化规则已明确，本阶段没有未解决的建模确认事项。文件结构不符是验证错误，不支持旧版 `.xls` 是软件格式限制，均通过明确的 `ValueError` 报错，不标为建模决策。此前审计报告及通用语义提示保持其只读口径不变。

## 问题一确定性调度

在项目根目录运行：

```bash
conda run --no-capture-output -n modeling_project python -X utf8 scripts/03_run_q1.py
conda run --no-capture-output -n modeling_project python -X utf8 -m unittest discover -s tests -v
```

`src/q1/optimizer.py` 只读加载冻结的 `data/processed/q1_input.csv`，复用公共时间解析和文件哈希检查，使用已有 PySCIPOpt/SCIP 实现连续线性规划。`x` 为外网向电池充电的电量，`y` 为外网直接供负载的电量，`q` 为光伏向电池充电的电量，`z` 为电池实际送达负载的电量，均为 kWh；SOC 是各 slot 结束后的电池内部电量。

SOC 递推采用 `S_i = S_(i-1) + 0.9*(x_i+q_i) - z_i/0.9`，初末 SOC 为 6000 kWh，范围 1200–10800 kWh。每个 slot 的充电端输入 `x+q` 和送达端放电量 `z` 分别不超过 `5000*10/60` kWh。供能满足 `pv-q+y+z >= load`，且 `0 <= q <= pv`。保留供能不等式以允许弃光；所有变量连续，不添加充放电互斥二进制变量。

一级最小化 `sum(price*(x+y))`，必须求得 `optimal` 才继续。随后以等式锁定一级最优费用 `C_star`，二级最小化 `sum(0.9*(x+q)+z/0.9)`。SCIP 可行性容差设为 `1e-9`；输出按绝对残差 `1e-6` 复核（能量 kWh、费用元），不裁剪近零变量。费用等式不人为放宽成本预算。二级同样必须达到 `optimal`。

| 文件 | 内容 |
| --- | --- |
| `outputs/schedule/q1_schedule.csv` | 完整 144 行，保留所有输入列，增加 `x_kwh/y_kwh/q_kwh/z_kwh/soc_kwh`，以及前一 SOC、购电量、充电端输入、电池内部充放电量、供能剩余、费用和吞吐量。 |
| `outputs/metrics/q1_metrics.json` | 两阶段状态及求解器目标、独立重算费用/吞吐量、SOC 指标、同充同放数量、各约束残差、容差、参数、冻结输入哈希及提交状态。 |
| `outputs/submissions/result1.xlsx` | 复制官方 `data/raw/附件5/result1.xlsx`，按 slot 1–144 顺序填写“计划购电量”B2:B145，另填充放电汇总及初末 SOC；保留原模板标签与格式。 |

入口必须先写出完整 CSV 与指标，再重新读取 CSV 独立复核全部约束、派生列和目标值；失败时禁止写 Excel。四小时汇总已确认固定使用 slot 1–24、25–48、49–72、73–96、97–120、121–144，模板充电量为 `sum(x+q)`，放电量为 `sum(z)`；效率仅用于 SOC 和吞吐量。初末储电量填写 6000 kWh。

结果写入规则已确认：购电量数值按 slot 行序填入模板，slot 1 对应 Excel 第 2 行，slot 144 对应第 145 行。官方时间段标签完全保留，不平移数值、不修改模板原件。默认运行即可在 CSV 与指标复核通过后生成 Excel，最终指标标记 `submission_status=written`。Q1 当前没有未解决的建模确认事项。

如后续另行确认其他映射，也可将按 slot 1..144 排列的 144 个官方区间标签保存为 JSON 字符串列表，再运行（当前默认行序规则不需要此参数）：

```bash
conda run --no-capture-output -n modeling_project python -X utf8 scripts/03_run_q1.py --interval-map path/to/confirmed_q1_intervals.json
```

`src/q1/result_writer.py` 默认按已确认的 slot 行序写入，也支持验证显式映射与模板标签一一对应后按标签定位，保留工作簿格式和其他单元格。测试中的反序映射仅用于验证可选映射，不构成正式时间规则。Q1 相关测试包括两阶段目标、独立约束计算、错误解拒绝、零负载二级优化、一级原始解对比、输入不变、默认行序写入及模板样式和汇总检查。

问题一诊断对比可随同一入口生成 `outputs/comparison/q1_primary_only_schedule.csv`、`q1_secondary_comparison.json` 和 `q1_secondary_comparison.md`。该诊断保存 SCIP 一级费用最优时实际返回的一个解，并与现有二级正式解比较吞吐量；正式调度、指标和提交副本已冻结，入口重复运行不会覆盖它们。

## 问题一论文图片入口

仅读取已保存的 Q1 输入、调度和指标，使用 matplotlib 生成图片，不调用优化器或修改数值结果：

```bash
conda run --no-capture-output -n modeling_project python -X utf8 scripts/04_plot_q1.py
```

图片统一保存于 `outputs/figures/q1/`，每图提供 **300 dpi PNG** 和 **PDF 矢量版**。论文手可直接打开 [图片索引与解读建议](outputs/figures/q1/README.md) 查找变量口径和用途。

| 图号 | 内容及用途 | PNG | PDF |
| --- | --- | --- | --- |
| 图1 | 电价与计划购电量：分析调度的经济响应 | [查看](outputs/figures/q1/q1_figure1_price_grid_purchase.png) | [矢量版](outputs/figures/q1/q1_figure1_price_grid_purchase.pdf) |
| 图2 | 负荷与光伏预测功率：说明日内供需特征 | [查看](outputs/figures/q1/q1_figure2_load_pv.png) | [矢量版](outputs/figures/q1/q1_figure2_load_pv.pdf) |
| 图3 | 储能充放电：正值充电、负值放电，识别运行阶段 | [查看](outputs/figures/q1/q1_figure3_battery_charge_discharge.png) | [矢量版](outputs/figures/q1/q1_figure3_battery_charge_discharge.pdf) |
| 图4 | SOC：展示初末状态及储电上下界 | [查看](outputs/figures/q1/q1_figure4_soc.png) | [矢量版](outputs/figures/q1/q1_figure4_soc.pdf) |
| 图5 | 购电用途分解：区分直接供负荷与充电，可选作附录图 | [查看](outputs/figures/q1/q1_figure5_grid_purchase_structure.png) | [矢量版](outputs/figures/q1/q1_figure5_grid_purchase_structure.pdf) |

## 许可证

本项目采用仓库中 `LICENSE` 文件所示许可证。竞赛官方提供的题目、数据、格式文件及其他附件仍受其原始版权和竞赛规则约束，不因存放在本仓库中而改变。

## 问题二实现与数值验收入口

正式计算范围为2025-02-01至2025-12-31，共334天、48096个10分钟时段。一月只用于历史回测和残差预热。只读取 `historical_power.csv` 的既有kWh列及 `q1_input.csv` 的固定日电价，不使用附件4电价；Q1与预处理数据保持冻结。本阶段不生成Q2图片，输出供数值验收。

```bash
conda run --no-capture-output -n modeling_project python -X utf8 scripts/05_run_q2.py
conda run --no-capture-output -n modeling_project python -X utf8 -m unittest discover -s tests -v
```

先执行 `python scripts/05_run_q2.py --benchmark`，将2月1日的完整滚动结果与耗时写入独立目录 `outputs/comparison/q2_rolling_benchmark/`，不覆盖正式结果。随后运行默认入口生成全年输出，再执行完整测试（单日和全年集成测试分别读取上述输出）。分步检查可加 `--skip-workbook`，先生成CSV与指标；默认命令完成全部输出。程序每5天显示进度，不输出逐次求解器日志。

当前正式实际运行模型依据《第二问(4)》由 ex-post perfect foresight recourse 更新为 causal rolling-horizon actual operation：0:00冻结日前预测和 `G_plan` → 只观测当前slot → 用当前真实值和未来冻结预测优化剩余时域 → 仅执行当前动作 → 重算真实SOC → 下一slot重新优化。每天固定日初真实SOC作为终端缺口参考，跨日继续传递真实末态，不每天重置为6000。预测、动态选窗、风险分位和日前两级模型保持原规则。

每次实际滚动使用同一个SCIP模型依次最小化紧急购电费用、日末SOC缺口 `delta>=max(0, day_start_soc-S_terminal)`、储能吞吐量；后级锁定前级最优值，不做加权折中。全年为48096次滚动、144288次实际LP优化。费用与吞吐量只累计真正执行的当前动作，不能累加彼此重叠的剩余时域目标。首个正式日基准总耗时约2.73秒，实际阶段2.70秒，其中432次优化约1.45秒，推算全年实际阶段约15分钟；完整运行实际阶段累计约14.02分钟。运行时间因设备与日期而异。

| 模块 | 职责 |
| --- | --- |
| `src/q2/forecasting.py` | 负荷同星期1/2/3/4周、光伏连续3/5/7/14天；每天在各自公共历史回测日上比较NMAE并动态选窗，缓存历史误差和以避免重复计算。 |
| `src/q2/risk.py` | 按slot取历史残差的逆经验CDF 80%分位数，保留负风险修正；拒绝空样本与目标日/未来残差。 |
| `src/q2/optimizer.py` | 保留日前费用/吞吐量两级LP及共用约束复核；`solve_actual_expost_legacy` 仅供旧版诊断，正式入口不调用。 |
| `src/q2/rolling.py` | 当前真实标量与冻结预测的安全接口，三级词典序求解、仅执行首个动作并从实际动作更新SOC。 |
| `src/q2/comparison.py` | 首次覆盖前复制并校验旧版结果；生成新旧全年购电、费用、SOC及四个指定日期的对比。 |
| `src/q2/result_writer.py` | 复制并按官方示例样式扩展输出模板，实际充放电六段汇总、紧急区间逐日合并及题面指定日期论文表。 |
| `scripts/05_run_q2.py` | 严格按历史预测→计划承诺→逐slot观测和滚动执行→更新历史和SOC顺序执行，写CSV并读回复核后才生成Excel。 |
| `tests/test_q2_*.py` | 预测/风险合成样本与全年因果性检查、优化手算案例与逐日约束复核、模板扩展和原文件完整性检查。 |

全部数值文件在 [outputs/q2/](outputs/q2/)：

| 文件 | 含义 |
| --- | --- |
| [q2_window_selection.csv](outputs/q2/q2_window_selection.csv) | 334天的动态窗口、所有候选NMAE、公共回测日期清单和风险样本日期清单。 |
| [q2_predictions.csv](outputs/q2/q2_predictions.csv) | 48096行实际/预测负荷与光伏、基线净负荷、Type-1风险修正及实现后的残差，能量单位均为kWh。 |
| [q2_plan_schedule.csv](outputs/q2/q2_plan_schedule.csv) | 日前变量、固定购电承诺、计划SOC、风险净负荷及逐slot计划费用。 |
| [q2_actual_schedule.csv](outputs/q2/q2_actual_schedule.csv) | 48096行真正执行的动作、当前真实供需、冻结预测、SOC与费用；滚动时域长度、三级目标/状态和残差仅作诊断。 |
| [q2_daily_metrics.csv](outputs/q2/q2_daily_metrics.csv) | 日初/计划末/实际末SOC、实际执行费用与吞吐、日末缺口、144次滚动的三级最优数量和最大残差、每日耗时。 |
| [q2_metrics.json](outputs/q2/q2_metrics.json) | 年度汇总、预测NMAE、选窗分布、紧急购电统计、状态和容差。 |
| [q2_warmup_predictions.csv](outputs/q2/q2_warmup_predictions.csv)、[q2_warmup_windows.csv](outputs/q2/q2_warmup_windows.csv) | 1月30日、31日的合法在线伪预测和选窗依据；这两天构成2月1日的初始残差样本。 |
| [q2_integrity.json](outputs/q2/q2_integrity.json) | 官方附件、Q1输出及预处理文件的运行前后SHA-256对照。 |
| [q2_paper_tables.md](outputs/q2/q2_paper_tables.md) | 自动提取3月20日、6月21日、9月23日、12月21日的指定购电时段、日费用、实际充放电和紧急购电区间。 |

提交文件为 [outputs/submissions/result2.xlsx](outputs/submissions/result2.xlsx)。计划表保留334天原行列和标签，填写48096个 `G_plan` 及计划日购电量/计划费用；充放电表在副本扩展至334×6行，填写实际 `x_real+q_real`、`z_real` 和日初/日末SOC。紧急购电仅报告 `e>1e-6 kWh` 的slot，按每日连续区间合并，不跨源日期合并，不生成零购电日期记录。区间端点沿用官方购电表的slot顺序与跨日标签；实际全年费用（含紧急费用）见每日指标及论文表。

新增行复制原模板示例块的字体、填充、边框、对齐、数字格式、行高及块内合并规则。原始模板不变，省略占位符仅在输出副本中被完整日期记录替代。

复核口径：SCIP可行性容差为1e-9；费用在前级最优值±1e-7元内锁定；实际运行二级缺口在最优值±1e-7 kWh内锁定。两者都只用于数值稳定性，不是建模权重。计划、每个剩余时域方案和真正执行序列均按1e-6独立验收。底层CSV不裁剪，论文展示将低于报告容差的残差显示为0。预测误差使用NMAE，不表述为分类准确率。

旧版结果完整保留在 `outputs/comparison/archive/q2_expost/`，包括原CSV、指标、论文表、result2副本及SHA-256清单；重复运行不会覆盖该存档。新旧对比见 [q2_expost_vs_rolling.md](outputs/comparison/q2_expost_vs_rolling.md) 和同名JSON。正式结果始终以新 `outputs/q2/` 和 `outputs/submissions/result2.xlsx` 为准。当前无未解决的Q2建模确认事项，结果待人工数值验收。

最新完整套件61项测试通过，覆盖审计、预处理、Q1及新Q2因果性、三级优先级、当前执行、全年复算和模板样式。Q1正式结果、图片、原始附件、预处理输入、预测与风险模块SHA-256均不变；新旧预测/风险输出逐字节一致。运行与校验数值见 `q2_metrics.json`，哈希对照见 `q2_integrity.json`。

## Q2 历史日曲线相似性图

运行 `conda run --no-capture-output -n modeling_project python -X utf8 scripts/06_plot_q2_lag_similarity.py`。唯一计算输入是 `data/processed/historical_power.csv` 中的实际 `load_kwh` 和 `pv_actual_kwh`，不调用预测或优化器。

`src/q2/lag_similarity.py` 按2025年源日期检查365×144条完整记录，按datetime排序；沿用冻结数据的日曲线归属，`0:00+1`保留为源日期最后一个slot。对滞后l=1..14，以第l+1日至第365日为有效目标日，计算与滞后日的绝对差总和，除以相同有效目标日的实际电量总和。

| 输出 | 用途 |
| --- | --- |
| [300 dpi PNG](outputs/figures/q2/q2_lag_similarity.png) | 两行子图，分别展示负荷和光伏的日滞后误差，供论文插图。 |
| [矢量 PDF](outputs/figures/q2/q2_lag_similarity.pdf) | 排版缩放使用，嵌入中文字体。 |
| [14行计算结果 CSV](outputs/metrics/q2/q2_lag_similarity.csv) | `lag_days`、`load_nmae`、`pv_nmae`，保留未取整计算值。 |

误差越小表示该滞后下日曲线越接近。虚线仅标注5、7、14天；此图是历史数据特征描述，不等同于预测模型的回测误差，也不据此更改已确认的预测窗口。新增 `tests/test_q2_lag_similarity.py` 的三项测试已通过，验证手算分母口径、完整性/跨年末点、输出格式和冻结文件哈希。

## Q3 第一阶段（单日及连续三日参考验证通过）

`src/q3/forecast.py` 校验附件3的冻结小时预报，使用发布时刻实测功率作为首小时左端点，线性插值后乘10/60得到电量；负荷预测直接复用Q2动态选窗函数。融合函数仅更新未执行slot。`src/q3/scenarios.py` 按最多14个合法历史日期同日配对负荷/融合光伏残差，等概率构造场景；按《第三问(6)》对场景预测加残差取max(0,·)，不修改数据或历史残差。

新增 `confidence.py` 按历史实际光伏>0评价剩余时域，最多7个历史日；无历史取0.5，无有效时段取0，epsilon固定1e-8，仅用于防除零。`forecast.py` 按同一机制逐日回放历史融合预报，负荷残差仍复用Q2动态选窗，合法成对残差从2025-01-30开始。

`optimizer.py` 实现共享购电场景计划和CVaR，计划无终端恢复约束，调整相对上一轮计划按1.5u−0.5v结算。实际层采用紧急费用→与最新计划终端SOC绝对偏差→吞吐量三级词典序，复用Q2物理约束验证器。`simulation.py` 只执行每轮当前一步，更新及跨日继承真实SOC；`metrics.py` 单独结算初始购电、各次增量调整和已执行紧急购电，不将风险目标计入实际费用。

运行命令（在项目根目录）：

```powershell
conda run --no-capture-output -n modeling_project python -X utf8 scripts/07_run_q3_single.py --alpha 0.95 --lambda 0.5 --days 1 --output-dir outputs/q3/single/smoke_one_day
conda run --no-capture-output -n modeling_project python -X utf8 scripts/07_run_q3_single.py --alpha 0.95 --lambda 0.5 --days 3
conda run --no-capture-output -n modeling_project python -X utf8 -m unittest discover -s tests -p "test_q3_*.py" -v
```

入口仅允许2025-03-20起始、首日6000kWh的1至3日 `TEST / REFERENCE ONLY` 验证；alpha/lambda显式传入。该入口不承担参数搜索、Score计算或result3.xlsx生成；已完成的20组实验及最终入口见下文。完整通过后在指定Q3目录保存六份 `q3_forecast_updates.csv`、`q3_confidence.csv`、`q3_scenarios_summary.csv`、`q3_plan_updates.csv`、`q3_actual_schedule.csv`、`q3_daily_metrics.csv` 及 `q3_single_metrics.json`。原始数据、预处理及Q1/Q2文件运行前后逐份核对SHA-256。

实际运行第二级参考值按团队确认定义为最新有效滚动计划的场景终端SOC概率加权期望，当前14个等概率场景等价于算术平均。加权函数支持非等概率输入并验证概率，不重选单个场景、不增加计划层终端恢复约束。每次0/6/12/18点计划完成后更新参考值，仅在下一次更新前沿用该值。

已完成2025-03-20单日144时段及03-20至03-22连续三日432时段验证，alpha=0.95、lambda=0.5，均为TEST / REFERENCE ONLY。三日实际费用76265.470158元，紧急购电748.019911kWh、15个有效时段；真实日末SOC依次1324.979516、1351.265017、1320.674143kWh，跨日传递误差0。所有计划两级及实际三级状态均optimal，最大约束误差1.00008e-7以内，无有效同时充放电。94个冻结文件SHA-256不变。

19项Q3测试及9项复用Q2预测/优化回归测试通过，独立复算场景加权参考、最新计划切换、合同增量结算、物理约束和跨日SOC；单日与三日首日输出逐值一致。完整逐日数值见 `outputs/q3/single/q3_daily_metrics.csv`，汇总见 `q3_single_metrics.json`，单日输出在 `smoke_one_day/`。当前Q3本阶段无未解除的建模确认事项，结果等待人工数值验收。

### Q3后续联合参数实验规则

`src/q3/parameters.py` 为统一候选来源：alpha为{0.80,0.85,0.90,0.95}，lambda为{0,0.25,0.5,1,2}，笛卡尔积共20组；参考入口与后续搜索共用，alpha=0.99不再合法。alpha=0.95保留为高风险厌恶参考。W_s=14等概率场景下，alpha达到13/14后经验CVaR等于最大损失。

`src/q3/search.py` 提供后续搜索的 `score_annual_results(daily_results)`：输入20组相同2025-02-01至12-31共334天的逐日实际结果，所需列为alpha、lambda、date、total_actual_cost_yuan、emergency_slot_count。该函数拒绝缺组、缺日、重复日期和旧候选，计算全年实际费用、有效紧急购电时段数以及日实际费用总体标准差(ddof=0)。三个指标分别使用全部20组的统一Min-Max上下界；极差≤1e-6时归一化统一为0。Score=0.5×归一化费用+0.3×归一化紧急时段数+0.2×归一化费用标准差，返回评分表及全部并列argmin参数，不添加并列选择偏好。参考三日结果不能用于正式评分。

全部20组使用相同全年流程、日期及初始化规则，仅改变alpha/lambda；联合实验现已完成并经过人工审查，最终winner见第三阶段结果说明。

本次更新后23项Q3测试全部通过，包含候选集合、旧alpha拒绝、20组全局上下界、总体标准差、近常量指标置零及不完整结果拒绝测试。

建模团队已接受SOC长期接近1200kWh下界的可能性；这是计划层无终端恢复/终端价值、实际层跟踪最新计划终态的模型结果。运行与结果分析应如实保留，不因此新增终端等式、惩罚、额外SOC目标，或修改目标函数及储能参数。

## Q3 第二阶段：单组正式全年参考

`scripts/08_run_q3_annual.py` 独立运行2025-02-01至12-31共334天、48096个执行时段；2月1日0:00真实SOC为6000kWh，随后仅继承前一日真实终态。首次年度验证使用alpha=0.90、lambda=0.50，标签为 `ANNUAL REFERENCE ONLY`，不是最终参数。07仍为1至3日参考入口。

```powershell
conda run --no-capture-output -n modeling_project python -X utf8 scripts/08_run_q3_annual.py --alpha 0.90 --lambda 0.50
conda run --no-capture-output -n modeling_project python -X utf8 -m unittest discover -s tests -p "test_q3_*.py" -v
```

可加 `--regression-only` 仅执行年度引擎与既有03-20至03-22参考结果的逐值比较。正式入口先通过这道1e-6等价门槛再运行全年，每完成10天输出进度。回归记录位于 `outputs/q3/annual/regression/`，既有 `outputs/q3/single/` 保持不变。

`src/q3/annual.py` 逐日维护参数无关缓存，每个历史日仅回放一次；原 `replay_history` 与年度路径共用 `replay_completed_day`。负荷预测及其候选误差缓存复用Q2算法，可信度使用最近7日、场景使用最近14个合法成对残差日，发布时刻光伏插值和场景构造仍按日内时间顺序执行。目标日及未来真实值不进入历史缓存；SOC、合同和求解结果不跨参数共享。本阶段未增加checkpoint/resume。

年度输出位于 `outputs/q3/annual/reference_a0.90_l0.50/`：六份预测更新/可信度/场景/计划/实际/逐日CSV以及 `q3_annual_metrics.json`。逐日执行轨迹及结算将由独立验证器复算，所有状态必须optimal、误差≤1e-6；紧急购电只在e>1e-6kWh时计有效时段。日末接近SOC下界按同一1e-6kWh数值容差统计。指标记录总体标准差(ddof=0)、初始与终末SOC、各更新时间累计调整量和rho、LP次数、加载/准备/首7天/全年耗时，以及保护文件SHA-256。

本阶段仅进行一组全年程序验收与性能benchmark，不运行20组联合搜索，不计算正式Score、不选择最终alpha/lambda、不生成result3.xlsx或最终论文表。

## Q3 第三阶段：20组联合全年实验

```powershell
conda run --no-capture-output -n modeling_project python -X utf8 scripts/09_run_q3_parameter_search.py
```

09入口使用 `parameters.py` 的20组笛卡尔积和同一 `annual.run_dates`，每组独立从6000kWh开始，默认且目前仅支持 `--workers 1`。启动前重新完整验收已有 `reference_a0.90_l0.50/`，该组只读复用；其他组逐个计算334天及48096个实际时段。可用 `--validate-only` 仅检查reference。

组级恢复由 `src/q3/search_runner.py` 管理。每组通过 `validate_annual`、状态及零有效同时充放电验收后，仅保存 `outputs/q3/search/groups/a{alpha}_l{lambda}/q3_daily_metrics.csv` 和 `q3_annual_metrics.json`。恢复必须验证完整日期、参数、摘要一致性、所有求解状态、误差、SOC连续、运行标签、摘要SHA-256和输入/模型指纹；失败组重算，不能凭文件存在跳过。不保存其他19组的大型调度/场景CSV，原reference完整明细不变。

所有20组成功才调用唯一的 `score_annual_results()`，在整个网格统一Min-Max，按已确认0.5/0.3/0.2权重计算Score，ddof=0、近常量指标置零；完全并列最优全部保留。结果写入 `q3_parameter_ranking.csv`、`q3_parameter_ranking.json`、`q3_parameter_search_summary.json` 和 `q3_all_daily_metrics.csv`，均位于 `outputs/q3/search/`。summary中的完成数、失败组和all_groups_valid反映当前状态；未全部完成时不生成最终排名。

20组联合实验全部完成，failed_groups为空（0组）、all_groups_valid=true。用户已人工审查并确认唯一winner=(0.85,0.25)，best Score=0.07674725274725275，无并列winner。排名及组摘要位于 `outputs/q3/search/`，冻结保留，不重新运行搜索。

## Q3 最终收尾：固定winner完整重跑

```powershell
conda run --no-capture-output -n modeling_project python -X utf8 scripts/10_run_q3_final.py
```

10入口固定 `src/q3/final.py` 中FINAL_ALPHA=0.85、FINAL_LAMBDA=0.25，不接受CLI参数覆盖。沿用年度引擎，从2025-02-01初始6000kWh连续运行334天、48096slot，预计约28分钟。正式重跑由用户执行；可加 `--check-only` 只核对已确认winner与模板，不执行优化。

完整结果写至 `outputs/q3/final/`，标记 `Q3 FINAL`。六份完整CSV及年度指标先落盘，再复用 `validate_annual` 独立复核并与搜索winner逐日/年度数值比较，容差1e-6；运行耗时和来源标签不要求相等。对比失败保存 `q3_search_vs_final_comparison.json` 诊断并停止，禁止写submission。

模板映射已由团队明确：计划表填写0:00原始g0及计划费用；调整表填写每slot三轮累计净变化Σ(u−v)，全天费用为ΣC(1.5u−0.5v)。保持四个sheet、原标题/列顺序/slot标签；只在输出副本中扩展全年充放电和实际紧急区间。充电用x_real+q_real、放电用z_real，每24slot汇总；e>1e-6kWh才合并为逐日紧急区间，不跨日。原始模板SHA-256始终核对，复用Q2样式块工具。仅Excel和论文显示层允许绝对值≤1e-6显示为0，不修改底层CSV。

通过后自动生成 `outputs/submissions/result3.xlsx`、`q3_final_validation.json`、`q3_final_summary.md`、`q3_paper_summary.md`、`q2_vs_q3_final_comparison.csv/.md`、`q3_update_time_summary.csv`、`q3_parameter_selection_table.csv`。论文表直接读取冻结排名，不重新评分；Q2比较只读其最终指标。当前候选网格与评价体系下的最优结果不表述为唯一理论最优，不虚构其他预测发布时间，不进入问题四。

<!-- Q3_FINAL_STATUS_BEGIN -->
最终全年完整重跑、搜索一致性对比、独立验收及result3.xlsx生成均已完成；论文交接文件已输出，等待人工最终审阅。
<!-- Q3_FINAL_STATUS_END -->

## Q4 动态电价代码及运行入口

代码实现阶段及轻量验证已完成：14项新增测试通过，含固定价格复现、未来数据扰动、临时模板及模拟搜索恢复。两种Q4各完成2025-03-20至03-22连续3日/432slot smoke，最大复算误差均约1e-7，204份冻结文件SHA一致。尚未执行334天正式Q4结果、Q4-3全年reference或真实20组全年搜索，未生成正式Q4提交。Q1/Q2/Q3代码及结果保持冻结，Git分支由用户管理。

`src/q4/price_forecasting.py` 每日用严格过去的公共回测日期，对同星期1/2/3/4周均值预测计算NMAE，复用Q2同精度选择较小窗口的规则。窗口每天重选，不固定为两周；原价格只读、不重新清洗或插值。选窗、候选误差及历史日期记录于 `q4_price_selection.csv`。

价格适配器只持有0:00预测c0与已揭示的真实价格。合同更新先用此前已执行slot的价格计算gamma；随后实际层揭示当前负荷、PV、价格，再刷新gamma，当前用真实价格、未来用gamma*c0。gamma每10分钟刷新，Q4-2合同全天固定，Q4-3合同仅在slot 1/37/73/109更新未执行尾部。`PRICE_EPSILON=1e-12`仅保护分母。`q4_price_refresh.csv` 保存每slot的gamma、观测数量、累加值及c0，可独立重建价格预测。

`q4_2.py` 复用Q2负荷/PV动态选窗、Type-1 tau=0.8历史风险及计划/实际求解器，保留负风险修正和当天真实日初SOC参考。`q4_3.py` 直接调用冻结Q3完整日循环，仅通过价格数组接口接入动态价格；保留W_c=7、W_s=14、可信度、成对场景、CVaR及实际三级词典序。两个实验各自初始6000kWh，之后独立传递真实SOC，不每日重置。

预测价格只用于决策。执行后按真实价格结算：Q4-2为原合同加5倍紧急购电；Q4-3为g0加三轮ΣC(1.5u−0.5v)加5倍紧急购电。预测目标与真实费用使用不同诊断列。

| 脚本 | 用途 | 输出目录 |
|---|---|---|
| `11_smoke_q4.py --days 3` | 两种Q4各连续1至3日TEST ONLY验证，默认从2025-03-20开始 | `outputs/q4/smoke/q4_2/`、`q4_3/` |
| `12_run_q4_2.py` | 用户以后运行独立334天Q4-2 | `outputs/q4/q4_2/` |
| `13_run_q4_3_reference.py` | 用户以后运行固定0.85/0.25的334天参考，禁止覆盖参数 | `outputs/q4/reference/q4_3_a0.85_l0.25/` |
| `14_run_q4_3_search.py` | 用户以后运行完整20组，可加`--resume`恢复 | `outputs/q4/search/` |
| `15_write_q4_results.py` | 全年结果人工验收后复制并填写官方模板 | `outputs/submissions/result4-2.xlsx`、`result4-3.xlsx` |

在项目根目录运行轻量验证：

```powershell
conda run --no-capture-output -n modeling_project python -X utf8 scripts/11_smoke_q4.py --days 3
conda run --no-capture-output -n modeling_project python -X utf8 -m unittest discover -s tests -p "test_q4*.py" -v
```

以后由用户执行的长任务：

```powershell
conda run --no-capture-output -n modeling_project python -X utf8 scripts/12_run_q4_2.py
conda run --no-capture-output -n modeling_project python -X utf8 scripts/13_run_q4_3_reference.py
conda run --no-capture-output -n modeling_project python -X utf8 scripts/14_run_q4_3_search.py --resume
```

Q4-3 reference标记 `Q4-3 PROVISIONAL / PAPER REFERENCE ONLY; NOT FINAL Q4-3 PARAMETER`。正式搜索alpha={0.80,0.85,0.90,0.95}、lambda={0,0.25,0.5,1,2}，每组独立初态及相同334天流程，直接复用Q3统一20组Min-Max、ddof=0、0.5/0.3/0.2 Score及近常量置零规则。恢复时核对输入/代码及已完成组SHA。汇齐20组才评分，唯一winner完整明细另存 `outputs/q4/final/`等待人工验收；若并列，不擅自指定最终组。

每个运行目录保存 `q4_actual_schedule.csv`、`q4_daily_metrics.csv`、价格选窗及刷新CSV、`q4_metrics.json`、`q4_validation.json`。Q4-2另有计划和负荷/PV选窗明细；Q4-3另有预测更新、可信度、场景及合同明细。运行记录进度和runtime_seconds。CSV保留原求解浮点数，独立验收复算约束、合同尾部、费用、价格观测与跨日SOC。

提交沿用Q2/Q3确认口径：官方slot顺序，连续24slot汇总充/放电x_real+q_real及z_real，e>1e-6按日合并紧急区间；Q4-3调整表为累计净变化及真实净调整费。仅扩展输出副本，保留原标题、列顺序及样式。用户人工验收全年结果后才能执行：

```powershell
conda run --no-capture-output -n modeling_project python -X utf8 scripts/15_write_q4_results.py --variant 2 --human-approved
conda run --no-capture-output -n modeling_project python -X utf8 scripts/15_write_q4_results.py --variant 3 --human-approved
```

reference或smoke不能提交。冻结数据、Q1/Q2/Q3源码及既有结果在所有入口前后核对SHA-256。以上为既有Q4入口说明；当前reference模型检验阶段停止Q4参数搜索和SCIP故障调试，不重新计算正式/参考结果。

## reference 分支模型检验

入口为 `scripts/16_run_model_validation.py`，仅允许在 `reference` 分支运行。`src/analysis/ablation_adapters.py` 通过局部依赖注入复用正式代码；`src/analysis/model_validation.py` 负责只读验收、冻结SHA保护、实验运行和论文表格。正式数据、Q1–Q4源码及原有输出均只读，全部新输出进入 `outputs/model_validation/`。

| 阶段 | 命令参数 | 内容与输出 |
|---|---|---|
| 只读验收 | `accept` | `q4_reference_acceptance.json/.md`；固定0.85/0.25的334天reference独立复算，无重新求解 |
| Q2-A轻量验证 | `q2 --smoke` | 首日144slot，保存于 `q2_risk_ablation/smoke/` |
| Q2-A全年消融 | `q2` | 仅风险修正归零；`q2_risk_ablation/run/`保存完整明细；对比冻结Q2-B |
| Q3-C轻量验证 | `q3 --smoke` | 首日四轮更新，保存于 `q3_confidence_ablation/smoke/` |
| Q3-C全年消融 | `q3` | 固定0.85/0.25，06/12/18新预测直接替换剩余时域；历史回放同步生成本实验残差；对比冻结Q3-D FINAL |
| Q4-A轻量验证 | `q4 --smoke` | 首日因果预测均价、逐时真实价格揭示及真实结算 |
| Q4-A全年消融 | `q4` | 固定0.85/0.25，原0:00价格预测只保留均值；保存于 `q4_price_blind/`，对比冻结Q4-B |
| 汇总 | `summary` | `summary/model_validation_summary.csv/.md`、`model_validation_validation.json` |

从项目根目录执行，例如：

```powershell
conda run --no-capture-output -n modeling_project python -X utf8 scripts/16_run_model_validation.py accept
conda run --no-capture-output -n modeling_project python -X utf8 -m unittest discover -s tests -p "test_model_validation.py" -v
```

全年实验严格串行，仅对消融模型各运行一次。入口用 `attempt.json` 记录运行状态，已有记录时拒绝自动重算；失败不重试、不改容差。日状态、成本及约束由磁盘明细复核。`integrity.json` 保存前后SHA及差异，任意冻结文件变化均报错。

本次运行状态：Q4只读验收通过；Q2-A在2025-07-02 slot119实际第三级LP出现SCIP数值错误并停止，未完成全年比较，不可把首日smoke或部分运行当作全年消融结果。失败原文及定位保存在 `q2_risk_ablation/run/attempt.json`，正式文件SHA未变。

Q3-C已完成334天、48096slot，独立复核最大违约1.519702e-7、跨日SOC误差0，冻结SHA不变。Q3-C全年实际费用14341250.59元；Q3-D为14156428.00元，差值-184822.59元（-1.28875%）。正式融合模型的调整费用较消融降低188189.78元，但紧急购电量增加1939.02kWh；完整十项指标和三次更新时间分解见下列文件，不将其概括为所有指标均改善。

论文手优先查看：

- `outputs/model_validation/q2_risk_ablation/q2_risk_ablation_metrics.csv`、`q2_risk_ablation_paper_summary.md`。
- `outputs/model_validation/q3_confidence_ablation/q3_confidence_ablation_metrics.csv`、`q3_confidence_ablation_by_update.csv`、`q3_confidence_ablation_paper_summary.md`。
- 各目录同名JSON与 `_validation.json` 记录结果和验收；只有全年状态为 `validated` 时才使用其数值。
- 差值定义为正式模型减消融模型，百分比以消融模型为分母；分母绝对值不超过1e-6时记null。每日费用标准差为334天总体标准差（ddof=0），不自动把变化称为改善。

Q4参考在新验收报告中标记 `Q4-3 fixed-parameter final candidate`，描述为“第四问固定沿用第三问风险参数进行动态电价分析”；团队已确认固定采用 `alpha=0.85、lambda=0.25`，不再进行Q4参数搜索。历史文件原标签保持不变，不能解释为Q4重新搜索得到最优参数。

Q4价格盲口径已确认，但该消融已按团队决定停止；不再运行或调试，也不进入正式定量比较。全年状态见 `q4_price_blind/run/attempt.json`，失败审计保留。

本次唯一Q4-A全年尝试在2025-03-22 slot142的实际层 `solve_actual_step()` 出现SCIP LP错误，已停止，耗时263.22秒，冻结SHA一致。`q4_price_blind.json`、`q4_price_blind_validation.json`、`q4_price_blind_paper_summary.md`记录失败；未生成全年指标CSV，不可把smoke当作全年效果。未重试、修改容差或开展故障调试。

Q4-A 已按决定停止；其失败记录不进入正式量化比较。模型检验论文摘要只纳入完整验收的 Q3-C/D、已验证Vdk和正式可行性验收；Q2-A不再重跑。

停止后4项价格盲专用测试与9项实验层回归合计13项通过，记录位于 `q4_price_blind/tests/results.json`；冻结文件SHA一致。这不代表全年LP运行成功。

`q4_reference_price_charge_slots.csv` 保存date、slot、real_price、charge_kwh、discharge_kwh，未计算低价充电/高价放电比例：`TODO: 需建模手确认低价/高价定义`。

Q3 Vdk = EXTERNAL VALIDATED DIAGNOSTIC。已从团队验证提交 `c5c5bf959c8ef54828ac1618ea1ee97f4a7443e8` 独立补回 `outputs/model_validation/q3_information_value/`，入口 `scripts/18_analyze_q3_information_value.py` 只读显示，不重新计算。Vdk 表示新增预测触发重新优化的条件调整经济价值；不同更新时间未来区间重叠，合计不等于全年真实节省。

实验层9项测试通过；Q2/Q3数值回归及固定价格Q4→Q3逐值回归通过。当前仍有1项Q4旧冻结清单测试未通过，因为其要求整个outputs清单与历史完全相等，而本次新增了model_validation输出；差异清单见 `outputs/model_validation/tests/integrity_restoration_and_legacy_diff.json`，不存在实验目录之外的差异，未修改旧清单。既有Q2绘图测试会重写原PDF元数据，因此不建议在冻结结果阶段直接批量运行所有带绘图入口的测试；本次副作用已按测试前SHA逐字节恢复。测试日志、复核及SHA记录保存在 `outputs/model_validation/tests/`。
