# Q4最终导出前只读验收

状态：READY_FOR_HUMAN_APPROVAL

未调用优化器，未生成正式result4。临时文件为NOT_FOR_SUBMISSION，仅用于验收。

## Q4-2
来源：outputs/q4/q4_2
年度数值验收：True；334天、48096slot；最大误差3.710986788973969e-07；跨日SOC误差0.0
NaN=0，Inf=0；临时Excel verify_values=True。
来源门槛：True

## Q4-3
来源：outputs/q4/reference/q4_3_a0.85_l0.25
年度数值验收：True；334天、48096slot；最大误差1.6389094525948167e-07；跨日SOC误差0.0
NaN=0，Inf=0；临时Excel verify_values=True。
来源门槛：True

本轮冻结SHA一致：True。逐项结果见JSON。历史protected SHA未擅自迁移或忽略。

时间映射沿用已确认的slot原行序，不宣称模板标签与模型时钟相同：模型slot1为00:00–00:10，官方首列仍为0:10–0:20；06/12/18更新从slot37/73/109生效。边界对照见template_precheck.json，未移动数值或改写官方标签。

紧急表原空白日期单元格General在写入datetime时按既有writer行为获得日期格式；其他字体、边框等属性已核验。未修改render_copy或verify_values。
