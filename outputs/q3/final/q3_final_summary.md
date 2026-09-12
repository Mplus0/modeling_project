# Q3最终结果交接

最终参数alpha=0.85、lambda=0.25。
20组联合全年实验在统一Min-Max及0.5/0.3/0.2权重下比较，唯一winner的Score=0.07674725274725275。
这是在当前候选网格与当前评价体系下的最优参数，不是唯一理论最优参数。

334天、48096个实际执行时段；最终完整重跑已通过年度独立验收及与搜索winner的逐值对比。

| metric | value |
| --- | --- |
| total_actual_cost_yuan | 14156427.999492 |
| total_plan_cost_00_yuan | 13401605.007782 |
| total_adjustment_cost_yuan | 248788.412508 |
| total_emergency_purchase_kwh | 125055.378164 |
| total_emergency_cost_yuan | 506034.579202 |
| emergency_slot_count | 2409.000000 |
| emergency_day_count | 252.000000 |
| daily_cost_std_yuan | 15303.096917 |
| initial_soc_kwh | 6000.000000 |
| final_soc_kwh | 1200.000000 |
| minimum_soc_kwh | 1200.000000 |
| maximum_soc_kwh | 10800.000000 |
| average_day_end_soc_kwh | 1368.187614 |
| days_ending_near_soc_min | 58.000000 |
| max_constraint_violation | 0.000000 |
| cross_day_soc_max_difference | 0.000000 |
| simultaneous_slots | 0.000000 |

## 预测更新汇总

| update_time | rho_mean | increase_kwh | decrease_kwh |
| --- | --- | --- | --- |
| 06:00 | 0.621234 | 208422.553039 | 451394.284103 |
| 12:00 | 0.634884 | 59904.587077 | 323619.627214 |
| 18:00 | 0.500609 | 128089.351190 | 3596.473073 |

# Q2与最终Q3结果比较

差值为Q3−Q2；百分比基准为Q2，零基准记为不适用。

| metric | q2 | q3 | absolute_difference | percentage_change |
| --- | --- | --- | --- | --- |
| total_actual_cost_yuan | 14388572.952429 | 14156427.999492 | -232144.952937 | -1.613398 |
| total_emergency_purchase_kwh | 277409.427003 | 125055.378164 | -152354.048839 | -54.920285 |
| total_emergency_cost_yuan | 1194359.088966 | 506034.579202 | -688324.509764 | -57.631287 |
| emergency_slot_count | 3282.000000 | 2409.000000 | -873.000000 | -26.599634 |
| emergency_day_count | 230.000000 | 252.000000 | 22.000000 | 9.565217 |
| initial_soc_kwh | 6000.000000 | 6000.000000 | 0.000000 | 0.000000 |
| final_soc_kwh | 2748.528969 | 1200.000000 | -1548.528969 | -56.340282 |
| average_day_end_soc_kwh | 3231.270543 | 1368.187614 | -1863.082929 | -57.657906 |
| simultaneous_slots | 0.000000 | 0.000000 | 0.000000 | 不适用 |
| max_constraint_violation | 0.000000 | 0.000000 | 0.000000 | 不适用 |

## 求解状态

{'plan_primary': {'optimal': 1336}, 'plan_secondary': {'optimal': 1336}, 'actual_primary': {'optimal': 48096}, 'actual_secondary': {'optimal': 48096}, 'actual_tertiary': {'optimal': 48096}}

result3.xlsx状态：已生成outputs/submissions/result3.xlsx并验证

待确认事项：无

## 可直接引用的数据说明

模型利用00:00、06:00、12:00和18:00四个预测发布时刻进行滚动更新。由于附件未提供其他发布时间的独立预测版本，无法在不引入额外假设的情况下对其他时刻进行同等级定量评估。
SOC低位运行按已确认模型如实保留，未增加终端恢复或储能储备目标。
相较Q2，Q3总实际费用变化-1.6134%。
相较Q2，Q3紧急购电量变化-54.9203%。
相较Q2，Q3紧急购电费用变化-57.6313%。
