# Q4-3计划二级LP异常诊断（2026-09-13）

## 已确认与尚未取得的证据

- 用户日志确认失败组：alpha=0.90、lambda=0.25，第12/20组。
- 最后一条成功进度：110/334天，2025-05-21。因此失败日在2025-05-22至2025-05-31之间；精确日期、update_time、horizon、场景数、start_soc、primary_star及输入范围均未被当时的程序保存。
- 栈位置为冻结`solve_plan`的第二次`model.optimize()`，发生在一级成功、添加双侧cost lock及设置throughput目标之后。
- 现有搜索引擎只有整组完成后才写出结果，没有该组中间SOC/合同检查点。没有本次真实NPZ；旧`last_negative_input.npz`属于0.80/0、9月22日的另一故障，未用于冒充此次复现。
- 本次真实二级LP复现次数为0，无法判断是否稳定复现，也不能给出真实primary_star或锁定相对精度。需要真实输入或同组中间状态；从初态重放至失败属于多日重放，超出此次只重放单案例的授权，尚未执行。

## 根因与处理边界

日志证明SCIP在二级LP求解中遇到数值困难；窄成本锁、变量/目标尺度及退化是待验证方向，不能仅凭报错确认是哪一个原因。没有证据表明模型数学不可行。

此次仅增加Q4局部观察器：保存精确NPZ、一级star/状态、price/load/PV/previous plan范围、grid/zeta/xi一级解尺度、cost lock实际浮点端点和余量；异常时尽可能导出CIP及SCIP参数。成功路径仍调用原Q3计划函数，所有参数、约束和两个目标均未修改。

推荐下一步是取得同一失败LP，原样重放最多3次并核对失败阶段，然后才比较Q4局部二级模型重建或数值缩放等方案。目前没有实验依据选择永久修复；没有放大容差、移除目标、改用加权和或跳过组。涉及数学口径的方案必须交建模手确认。

## SHA差异（与LP错误分开）

完整逐文件before/after哈希见`plan_failure_search_audit.json`，路径清单见`plan_failure_search_audit.md`。

搜索启动后新增12个受保护输出：

- `outputs/figures/q3/q2_q3_annual_relative_comparison.csv`
- `outputs/figures/q3/q2_q3_annual_relative_comparison.png`
- `outputs/q3/diagnostics/information_value/`下的`q3_information_value.json`、`q3_information_value_by_update.csv`、`q3_information_value_paper_summary.md`、`q3_information_value_summary.csv`、`q3_information_value_validation.json`
- 同目录`smoke/`下的上述5个同名文件。

这12项均为新增论文/事后诊断输出，不是Q4数学输入；没有原有冻结输入、Q1/Q2/Q3代码、正式结果的修改或删除。`protect`比较整个文件字典，因此新增文件也触发SHA异常。

当前manifest差异另外包含本次诊断新增`src/q4/plan_diagnostics.py`及修改`src/q4/q4_3.py`；二者属于本次记录器实现，不是此前运行失败的起因。

## 完整组与恢复

11组全部通过完整回执覆盖、逐文件SHA、参数/标签及`validate_outputs(..., formal=True)`检查：

- alpha=0.80，lambda=0、0.25、0.5、1、2。
- alpha=0.85，lambda=0、0.25、0.5、1、2。
- alpha=0.90，lambda=0。

现有组可以保留，没有删除/改写回执、progress或manifest。继续使用现有严格resume入口前，需要经用户审核的签名迁移；备份、逐项diff、批准记录及再验收方案见审计MD。当前不应直接启动`--resume`。

## 验证

- Q3：46/46项通过。
- Q4：21/22项通过；唯一失败为`test_saved_smoke_three_days_and_integrity`中旧冻结全目录清单的等值断言。三日数值检查先通过，再因上述新增输出失败；未改测试、未更新旧清单或关闭保护。
- 固定价格Q4→Q3逐值回归通过（绝对容差1e-6）；0.85/0.25参考参数的真实单日回归通过。
- 新增3项诊断测试通过：成功路径数值一致；一级故障正确记录null star；合成二级异常保留精确输入并可在撤销注入后重放。合成注入不代表真实故障复现。
- 未启动334天运行、真实20组搜索或正式submission。既有mock搜索/临时模板单元测试只使用夹具。

## 相关文件

新增`src/q4/plan_diagnostics.py`、`scripts/19_diagnose_q4_plan.py`、`tests/test_q4_plan_diagnostics.py`；修改`src/q4/q4_3.py`、`README.md`、`README_AI.md`。冻结Q3代码未修改。读取/验收和单LP重放用法见README。
