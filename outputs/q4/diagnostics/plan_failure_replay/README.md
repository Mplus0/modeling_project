# 单参数组路径重放诊断

固定alpha=0.90、lambda=0.25，从2025-02-01原始6000 kWh初态开始，复用当前Q4年度与日循环以及冻结Q3计划/实际数学实现。任意异常立即退出；不尝试数值修复，不运行其他参数组，不写入搜索或正式结果。

运行入口（只允许启动一次，`run_started.json`存在时拒绝重复执行）：

```powershell
conda run --no-capture-output -n modeling_project python -X utf8 outputs/q4/diagnostics/plan_failure_replay/run_path_replay.py
```

- `run_started.json`：本次单组诊断标签与参数。
- `path_progress.json`：最近完整执行日及计划更新次数。
- `active_plan_context.json/.npz`：当前计划的精确场景日期、概率、状态、合同与输入。
- `last_successful_plan.json/.npz`：失败前最近一次成功计划的输入、合同、终态与目标。
- `plan_failure_*.json/.npz/.cip/.set`：SCIP真实异常时保存的阶段、star、数值范围、独立LP输入、模型及参数。
- `failure_context.json`：失败上下文与求解器阶段记录。
- `exception.txt`：异常栈。
- `replay_result.json`：停止原因、最后日期、运行耗时与完整性结果。
- `sha256_before.json`、`sha256_after.json`：诊断目录之外的数据、代码、脚本、搜索记录及全部输出的逐文件SHA。

本次仍调用原`protect`并增加运行前后全量文件集合/hash核对。既有Q4 21/22中旧冻结清单与新增Q3论文/诊断输出不一致的问题单独保留；未修改旧清单或迁移搜索manifest。运行成功不意味着历史签名已经获准迁移。

本次所有文件（包括此说明和AI记录）仅写入本目录，根README及冻结源码不修改。本目录结果不是正式实验、reference或completed group。

## 三次独立LP复核结果

已在同一modeling_project环境对真实NPZ原样重放3次，全部在第二阶段出现`SCIP: error in LP solver!`。每次一级状态均为optimal，star均为118.6613023613645；在本环境和本输入下稳定可复现。没有改变求解设置、成本锁或模型，也未运行其他日期或参数。

结果详见`three_lp_replays_result.json`，完整性记录见`three_lp_replays_integrity.json`，每次失败的NPZ/JSON在`replay/`。CIP/SET导出仍因SCIP文件接口错误失败；相对路径也未消除此问题，未追加求解或修改导出实现。可独立重建输入的NPZ/JSON完整保留。

`run_three_lp_replays.py`仅用于本次已完成复核，启动标记存在时拒绝重复运行。汇总说明见`three_lp_replays_summary.md`。
