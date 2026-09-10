# 标准化预处理摘要

| 输入（数据行，不含表头） | 输出 | 输出行数 | 时间分辨率 | 缺失值 |
|---|---|---:|---|---|
| 附件 1：144 | q1_input.csv | 144 | 10 分钟，原时刻标签 | 0 |
| 附件 2：两表各 365 × 144 | historical_power.csv | 52560 | 10 分钟 | 0 |
| 附件 3：1460 × 24 | pv_forecast_hourly.csv | 35040 | 每 6 小时发布，预报步长 1 小时 | 0 |
| 附件 4：365 × 144 | electricity_price.csv | 52560 | 10 分钟 | 0 |

附件 3：365 个日组均按 00、06、12、18 时排列；1460 个唯一发布时刻，每次 24 条预报。
仅在派生时间中补全 1095 个展示用空白日期：位置为每个四行日组内原日期为空的非首行，取该组首行日期；原始表未变。

功率原值保留，新增电量列 = 功率 × (10/60)；电价原值保留。源时间字符串保留，Excel time 对象序列化为 HH:MM:SS；不构造区间标签。
0:00+1 属次日。目标时间 = 发布时刻 + horizon_hour 小时；目标时间可跨发布时刻重复，发布/目标组合唯一。未重采样或插值。
附件 5 未加载、未预处理；仅纳入哈希完整性检查。没有删除、裁剪或归一化任何数值。

SHA-256 完整性：通过（全部 9 个官方工作簿处理前后对比）。

| 原始文件 | 处理前 SHA-256 | 处理后 SHA-256 |
|---|---|---|
| 附件1.xlsx | 66b87134f5ecccd68184d3539bb1293ef039f9e0fdd955a589b9bfa7f227c377 | 66b87134f5ecccd68184d3539bb1293ef039f9e0fdd955a589b9bfa7f227c377 |
| 附件2.xlsx | 2e95fd446bfafa0d8c59577b5c2e2ea8b3f1def20dde54a3062556f4da9b4c72 | 2e95fd446bfafa0d8c59577b5c2e2ea8b3f1def20dde54a3062556f4da9b4c72 |
| 附件3.xlsx | 8a61b06c52bd0d639a1cc37c61a7d9f5b75edcbca718f64c1bd3498ec9f9d843 | 8a61b06c52bd0d639a1cc37c61a7d9f5b75edcbca718f64c1bd3498ec9f9d843 |
| 附件4.xlsx | 20e9c93aeab5e8e21ae4dd15587f9e190f7408692504c1319598461cd654fe71 | 20e9c93aeab5e8e21ae4dd15587f9e190f7408692504c1319598461cd654fe71 |
| 附件5\result1.xlsx | 28360e0974e7d6065394a8aba4e14a86773ae0036cc7d3ea1b211b515b03d688 | 28360e0974e7d6065394a8aba4e14a86773ae0036cc7d3ea1b211b515b03d688 |
| 附件5\result2.xlsx | 1c26494cfc6d754e0bd9bff7e13e1126a73d2d2da6c5336eb251d89b9a1a1a47 | 1c26494cfc6d754e0bd9bff7e13e1126a73d2d2da6c5336eb251d89b9a1a1a47 |
| 附件5\result3.xlsx | c59da470cabd0be23f602c95c8aa9d11ec224a0cdac216b3e1f218e65d006bdc | c59da470cabd0be23f602c95c8aa9d11ec224a0cdac216b3e1f218e65d006bdc |
| 附件5\result4-2.xlsx | 1c26494cfc6d754e0bd9bff7e13e1126a73d2d2da6c5336eb251d89b9a1a1a47 | 1c26494cfc6d754e0bd9bff7e13e1126a73d2d2da6c5336eb251d89b9a1a1a47 |
| 附件5\result4-3.xlsx | c59da470cabd0be23f602c95c8aa9d11ec224a0cdac216b3e1f218e65d006bdc | c59da470cabd0be23f602c95c8aa9d11ec224a0cdac216b3e1f218e65d006bdc |

未解决的建模确认事项：无（仅执行本阶段已明确的标准化规则）。
