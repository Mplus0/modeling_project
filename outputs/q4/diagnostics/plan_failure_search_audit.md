# Q4计划LP故障：搜索文件只读审计

失败组由用户日志确认为0.90/0.25；日期只能限定在2025-05-22至2025-05-31。没有本次真实LP输入，未进行伪造初态重放。

## 与搜索启动manifest的逐项差异

- added: `outputs\figures\q3\q2_q3_annual_relative_comparison.csv`
- added: `outputs\figures\q3\q2_q3_annual_relative_comparison.png`
- added: `outputs\q3\diagnostics\information_value\q3_information_value.json`
- added: `outputs\q3\diagnostics\information_value\q3_information_value_by_update.csv`
- added: `outputs\q3\diagnostics\information_value\q3_information_value_paper_summary.md`
- added: `outputs\q3\diagnostics\information_value\q3_information_value_summary.csv`
- added: `outputs\q3\diagnostics\information_value\q3_information_value_validation.json`
- added: `outputs\q3\diagnostics\information_value\smoke\q3_information_value.json`
- added: `outputs\q3\diagnostics\information_value\smoke\q3_information_value_by_update.csv`
- added: `outputs\q3\diagnostics\information_value\smoke\q3_information_value_paper_summary.md`
- added: `outputs\q3\diagnostics\information_value\smoke\q3_information_value_summary.csv`
- added: `outputs\q3\diagnostics\information_value\smoke\q3_information_value_validation.json`
- added: `src\q4\plan_diagnostics.py`
- modified: `src\q4\q4_3.py`

## 已有组验收

- outputs\q4\search\groups\a0.80_l0.00: 通过
- outputs\q4\search\groups\a0.80_l0.25: 通过
- outputs\q4\search\groups\a0.80_l0.50: 通过
- outputs\q4\search\groups\a0.80_l1.00: 通过
- outputs\q4\search\groups\a0.80_l2.00: 通过
- outputs\q4\search\groups\a0.85_l0.00: 通过
- outputs\q4\search\groups\a0.85_l0.25: 通过
- outputs\q4\search\groups\a0.85_l0.50: 通过
- outputs\q4\search\groups\a0.85_l1.00: 通过
- outputs\q4\search\groups\a0.85_l2.00: 通过
- outputs\q4\search\groups\a0.90_l0.00: 通过

## 待审核的签名迁移方案

不执行迁移。待真实故障诊断完成、用户批准后：先按时间戳备份原manifest与progress，记录备份SHA；逐项审核上述diff并重验完整组回执；仅把已批准的非计算输出新增及已测试的Q4诊断代码变更纳入新签名。记录旧/新签名、理由、批准记录和验证结果，再原子替换manifest。任何额外输入/模型/正式结果差异必须停止。保留原组回执及其原始来源签名，不改写已完成组。

目前不能直接使用--resume；未启动全年、参数搜索或提交。
