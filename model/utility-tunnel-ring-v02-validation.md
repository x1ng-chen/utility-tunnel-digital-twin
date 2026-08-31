# V02 三维资产验证记录

## 本轮按计划书补齐的可视功能

| 项目需求 | V02 模型资产 |
| --- | --- |
| A/B/C 三分区、透明罩和检修口 | `MESH_RING_*`、`MESH_ROOF_HATCH_*`、区域肋板/标签 |
| 封闭燃气管道与泄漏定位 | `MESH_PIPE_G01`、`MESH_LEAK_G01`、CH4/CO/O2 监测模块 |
| 气体报警后的通风与反馈 | `MESH_FAN_01`、`MESH_VENT_01`、`MESH_FAN_TACH_01`、`MESH_FAN_CURR_01` |
| 烟感和三分区温度异常 | `MESH_SMOKE_01`、`MESH_TEMP_A01/B01/C01`、`MESH_HEATER_01` |
| 受控渗水、接水盘和高水位保护 | `MESH_LEAK_W01`、`MESH_DRIP_W01`、`MESH_WATER_TRAY`、`MESH_HILEVEL_01` |
| 门禁、控制、联网、声光、急停 | `MESH_DOOR_CONTACT_01`、`MESH_CTRL_01`、`MESH_NET_01`、`MESH_ALARM_01`、`MESH_ESTOP_01` |
| 信号模拟安全边界 | `MESH_SIMBOX_01` |

## 重要表达修正

`PIPE-G01` 是封闭的燃气管道监测对象，不是课堂内的真实气体循环管。甲烷、CO、氧气模块保留环境基线采集；异常演示由隔离信号模拟盒表达。C 区风机和青色通风管是独立排风路径。

## 验证结果

- `MESH_PIPE_G01` 为闭合曲线，76 个控制点。
- 186 个对象；160 个原生网格对象；所有计划书关键功能资产都存在。
- 无非有限对象变换；透明封闭外壳和仅用于说明的剖视图分别已输出。
- `asset-map.json` 包含 21 个资产条目；GLB 二进制节点名可完整覆盖映射。
- GLB 能重新导入；导入后为约 169,472 个多边形，低于 200,000 建议上限；文件约 5.0 MB，低于 15 MB 目标。

## 证据

- `previews/utility-tunnel-ring-v02-hero.png`：完整透明外壳展示。
- `previews/utility-tunnel-ring-v02-functional.png`：仅用于功能说明的去壳剖视图，内部管道、传感器与安全组件清晰可读。
