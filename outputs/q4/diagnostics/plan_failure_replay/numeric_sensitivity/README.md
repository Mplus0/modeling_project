# SCIP纯数值参数敏感性诊断

当前环境：SCIP 10.0.2，SoPlex 8.0.2，PySCIPOpt 6.2.1。通过当前Model.getParams枚举实际可用参数及默认值，完整列表见available_parameters.json。SCIP默认feastol为1e-6，但项目原代码实际设置1e-9，本实验始终保持项目值。

唯一输入为alpha=0.90、lambda=0.25、2025-05-30 12:00、72时段、14场景的真实失败NPZ，其SHA已核对。每次一级沿用原设置；候选参数仅在第二次optimize之前应用，每个配置独立运行3次。其他数学表达及全部输入不变，COST_LOCK_TOLERANCE=1e-7、SOLVER_FEASTOL=1e-9、VALIDATION_TOL=1e-6完全不变。

| 配置 | 实际参数 | 原值 | 新值 | 一级optimal | 二级optimal | 二级LP错误 |
|---|---|---|---|---:|---:|---:|
| 默认对照 | 无 | — | — | 3/3 | 0/3 | 3/3 |
| 关闭LP scaling | lp/scaling | 1 | 0 | 3/3 | 0/3 | 3/3 |
| LP scaling模式2 | lp/scaling | 1 | 2 | 3/3 | 0/3 | 3/3 |
| Markowitz稳定性阈值 | lp/minmarkowitz | 0.01 | 0.1 | 3/3 | 0/3 | 3/3 |
| 更频繁重分解 | lp/refactorinterval | 0 | 10 | 3/3 | 0/3 | 3/3 |
| 关闭LP presolving | lp/presolving | true | false | 3/3 | 0/3 | 3/3 |

没有把LP重分解参数宣称为iterative refinement。枚举未发现独立的LP iterative-refinement控制参数，未假设存在或硬编码此类参数。

18次一级均optimal，primary_star均为118.6613023613645，与原真实路径一致。18次二级均出现SCIP: error in LP solver!及unresolved numerical troubles in LP 2。逐次配置、阶段状态、耗时和错误见results.json，每次Python完整异常栈见对应error.txt；SCIP原生标准错误共同内容另存solver_stderr_common.txt。

二级未取得可验收解，secondary objective、最终primary value、primary保留误差、最大约束违约、throughput、CVaR、grid范围均记null，不将失败解释为零误差。未找到3/3成功配置，因此未运行10次稳定性验证，未进入Q4永久适配或新增Q3/Q4/fixed-price/reference回归。本轮不报告这些条件性回归已通过；此前固定价格回归结果不等于存在可用的新配置。

代码仅为上级numeric_sensitivity.py中的Q4隔离诊断。未修改src/q3、src/q4正式代码、数学模型、求解容差、输入数组、原论文/正式结果、搜索签名或回执。integrity.json确认404份保护文件SHA不变。

结论仅针对本轮少量配置及“二级前设置”的应用方式，不意味着穷尽SCIP参数空间。不建议将任一受测配置用于Q4。按用户规定到此停止，不再增加组合或更改成本锁等数学口径。

纯SCIP数值参数方案未解决，后续需建模手确认模型层处理。
