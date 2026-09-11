# 问题一论文图片索引

PNG：300 dpi；PDF：矢量版，适合论文排版与编辑。

横轴只依据 slot 顺序：区间量位于 slot 中点，SOC 位于边界，0、24、…、144 对应 0:00、4:00、…、24:00。此为统一绘图表示，不改动源标签或官方模板映射。

| 图 | 文件 | 使用变量 | 物理含义与论文建议 |
|---|---|---|---|
| 图1 电价与计划购电量时序变化 | [PNG](q1_figure1_price_grid_purchase.png) / [PDF](q1_figure1_price_grid_purchase.pdf) | price_yuan_per_kwh、grid_purchase_kwh | 展示电价与计划购电量的时序关系，可分析调度的经济响应；不据此声称低价必然对应高购电量。 |
| 图2 小区负荷与光伏预测功率 | [PNG](q1_figure2_load_pv.png) / [PDF](q1_figure2_load_pv.pdf) | load_kw、pv_forecast_kw | 展示输入功率的日内供需特征；光伏为预测值，不是实测曲线或预测精度评价。 |
| 图3 储能设备充放电时序 | [PNG](q1_figure3_battery_charge_discharge.png) / [PDF](q1_figure3_battery_charge_discharge.pdf) | charge_input_kwh、z_kwh | 正柱为充电端输入 x+q，负柱为实际送达负载的放电量 −z，用于识别储能运行阶段。 |
| 图4 储能设备储电量变化 | [PNG](q1_figure4_soc.png) / [PDF](q1_figure4_soc.pdf) | soc_previous_kwh 首值、soc_kwh | 展示初末储电量及上下界，用于说明储能状态变化与容量利用。 |
| 图5 外网购电用途分解 | [PNG](q1_figure5_grid_purchase_structure.png) / [PDF](q1_figure5_grid_purchase_structure.pdf) | x_kwh、y_kwh | 分解购电用于储能与直接供负荷的比例，堆叠不包含光伏 q；篇幅有限时可放附录。 |

充放电柱图使用 x+q 和 z，不使用效率调整后的内部电量；小于验证容差的残差仅在绘图副本中显示为零。
所有图仅展示已保存结果；不重新求解，不表示预测准确率。绘图数据校验通过，本阶段无新增建模待确认项。
