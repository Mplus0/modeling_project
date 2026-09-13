# 模型检验汇总

- Q2-A vs Q2-B: stopped。2025-07-02 slot 119 tertiary 数值求解失败；按团队决定不再运行，未形成完整全年比较
  D:\Desktop\数学建模\modeling _project\outputs\model_validation\q2_risk_ablation

- Q3-C vs Q3-D: validated。
  D:\Desktop\数学建模\modeling _project\outputs\model_validation\q3_confidence_ablation

- Q4-A vs Q4-B: not included in formal quantitative comparison due to solver numerical failure。未形成有效全年实验结果，不纳入正式定量比较；沿用既有Q4-3 reference
  D:\Desktop\数学建模\modeling _project\outputs\model_validation\q4_price_blind

- Q3 Vdk: validated external diagnostic。已从团队验证提交 `c5c5bf959c8ef54828ac1618ea1ee97f4a7443e8` 核对并补回，本分支不重新计算。
  

- Q4 low/high price ratios: pending modeler confirmation。TODO: 需建模手确认低价/高价定义
  D:\Desktop\数学建模\modeling _project\outputs\model_validation\q4_reference_price_charge_slots.csv

正式可行性验收：Q1、Q2、Q3及Q4 reference 的冻结结果已完成年度约束、SOC连续性、求解状态和SHA核对；详见 `formal_feasibility_validation.json`。Q4-3固定参数为 alpha=0.85、lambda=0.25。

# Q3-C vs Q3-D

差值为Q3-D减Q3-C，百分比以Q3-C为分母；零基准记null。每日标准差ddof=0。

| metric | Q3-C | Q3-D | difference | relative_change_percent |
|---|---:|---:|---:|---:|
| total_actual_cost_yuan | 14341250.590852704 | 14156427.999491744 | -184822.59136096016 | -1.288748078071 |
| plan_cost_yuan | 13401558.75262501 | 13401605.007781535 | 46.25515652447939 | 0.000345147586026 |
| emergency_purchase_kwh | 123116.35331853734 | 125055.37816386891 | 1939.0248453315726 | 1.574953117978372 |
| emergency_cost_yuan | 502713.6431019929 | 506034.5792017333 | 3320.9360997403855 | 0.660601944130372 |
| emergency_slot_count | 2444.0 | 2409.0 | -35.0 | -1.432078559738134 |
| emergency_day_count | 252.0 | 252.0 | 0.0 | 0.0 |
| daily_cost_std_yuan | 15481.941761698154 | 15303.09691701403 | -178.84484468412302 | -1.155183551501141 |
| adjustment_cost_yuan | 436978.19512569834 | 248788.41250847516 | -188189.7826172232 | -43.06617234370006 |
| final_soc_kwh | 1200.0000000519697 | 1200.0000000519697 | 0.0 | 0.0 |
| simultaneous_slots | 0.0 | 0.0 | 0.0 | None |

数值只描述本次消融差异，不自动判定所有指标改善或统计显著性。
