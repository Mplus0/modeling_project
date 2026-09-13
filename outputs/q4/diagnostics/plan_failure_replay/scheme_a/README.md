# 方案A：全新二级Model实验（2026-09-13）

同一真实快照：alpha=0.90、lambda=0.25、2025-05-30 12:00、first_slot=73、horizon=72、14个场景。

## 实现

诊断入口为上级目录`scheme_a.py`，通过AST直接复用冻结`solve_plan`的全部变量/约束构造语句。一级按原模型与设置求解成功后，保存一级grid，释放原Model，重新执行完全相同的构造语句创建全新Model；随后沿用原双侧primary lock和throughput目标。独立验收及输出提取也直接复用原语句。未修改src/q3、正式Q4入口、数学公式、COST_LOCK_TOLERANCE=1e-7或SOLVER_FEASTOL=1e-9。

## 真实输入三次结果

| 实验 | 一级状态 | primary_star | 二级结果 | 秒 |
|---|---|---:|---|---:|
| 原实现（已有对照） | 3/3 optimal | 118.6613023613645 | 3/3 LP错误 | 见原重放记录 |
| 方案A第1次 | optimal | 118.6613023613645 | LP错误 | 0.4776974 |
| 方案A第2次 | optimal | 118.6613023613645 | LP错误 | 0.4521709 |
| 方案A第3次 | optimal | 118.6613023613645 | LP错误 | 0.4876690 |

三次均为`SCIP: error in LP solver!`，终端同时报告`unresolved numerical troubles in LP 2`。方案A成功率0/3；一级star相对原对照的差异均为0。

二级没有可验收的最优解，因此secondary objective、最终primary value、primary保留误差、最大约束违约、二级grid差异、CVaR及throughput均记为null，不能填0或当作通过。

结论：新建二级Model仍稳定失败，单纯状态重建不足以修复，不能将根因单独归于freeTransform后的状态复用。不建议将方案A作为永久修复。

保护的404份目录外文件前后SHA不变；详细结果与完整性分别见`results.json`和`integrity.json`。没有运行多日路径、其他参数、搜索或提交。用户要求的成功后Q3/Q4及reference回归没有触发，本轮未重跑该套测试，也未改变既有测试/旧冻结清单状态。

按用户的失败停止条件，当前停止。下一步仅可在单案例上评估SCIP内部缩放/数值参数，尚未实施。当前无数学改动需要确认；任何放宽成本锁、改变目标、CVaR或SOC的方案仍需建模手确认。

本次所有新增代码、说明和结果均限定于Q4诊断目录，未修改根文档或正式源码。
