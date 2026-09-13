# Q4 reference只读验收

Q4-3 fixed-parameter final candidate。第四问固定沿用第三问风险参数进行动态电价分析。

未重新求解，未修改历史PROVISIONAL标签；不是Q4重新搜索得到的最优参数。

- branch: reference
- head: 85844f27769220761d4c06108a294e37ca21f00d
- passed: True
- days: 334
- slots: 48096
- max_constraint_violation: 1.6389094525948167e-07
- cross_day_soc_max_difference: 0.0
- total_actual_cost_yuan: 14943845.120157544
- plan_cost_yuan: 14161676.303749995
- emergency_purchase_kwh: 123694.10591227323
- emergency_cost_yuan: 514221.0113005898
- emergency_slot_count: 2357
- emergency_day_count: 261
- daily_cost_std_yuan: 19800.1572751108
- adjustment_cost_yuan: 267947.80510696035
- final_soc_kwh: 1200.0000000481
- simultaneous_slots: 3
- initial_soc_kwh: 6000.0
- minimum_soc_kwh: 1199.9999999999998
- maximum_soc_kwh: 10800.000000000002
- alpha: 0.85
- lambda: 0.25
- label: Q4-3 fixed-parameter final candidate
- description: 第四问固定沿用第三问风险参数进行动态电价分析
- original_label: Q4-3 PROVISIONAL / PAPER REFERENCE ONLY; NOT FINAL Q4-3 PARAMETER
- solver_status_counts: {'plan_primary': {'optimal': 1336}, 'plan_secondary': {'optimal': 1336}, 'actual_primary': {'optimal': 48096}, 'actual_secondary': {'optimal': 48096}, 'actual_tertiary': {'optimal': 48096}}
- parameter_adoption: TODO: 需建模手确认；仓库现有文档未发现固定沿用参数的明确确认
- source: outputs/q4/reference/q4_3_a0.85_l0.25
- validation_tolerance: 1e-06

SHA-256：全部受保护文件与验收前一致。
