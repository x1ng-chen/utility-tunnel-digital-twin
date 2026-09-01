# 综合管廊模型连续版本索引

模型迭代从 V10 起按连续整数编号维护。文件名中的第二段仅描述该版本主题，
不代表额外版本号；项目计划书版本在文档中单独维护。

| 版本 | 文件主题 | 备注 |
|---|---|---|
| V10 | `annular` | 环形实体基线。 |
| V11 | `hardware-baseline` | 原 `v11-v35` 已重命名；V3.5只表示当时采用的硬件台账基线。 |
| V12 | `distributed-sensors` | 将传感器分布到多个站点。 |
| V13 | `annular-stations` | 环形站点细化。 |
| V14 | `fabrication-detail` | 加工细节检查点。 |
| V15 | `level-fan-pump` | 液位、风机与泵的可视化。 |
| V16 | `distributed-levels` | 5个液位站分散布置。 |
| V17 | `fabrication-waterloop` | 待安全评审的低水量路径。 |
| V18 | `fabrication-safety` | 加工尺寸门槛、干湿隔离与锁定状态。 |
| V19 | `clarity-layout` | 1.00×0.50×0.30m清晰分区与照片比例软管视觉路径。 |
| V20 | `visible-water-piping` | 仅用于审查的可见水路表达。 |
| V21 | `engineering-baseline` | A/B/C三区桌面式工程基线。 |
| V22 | `sensor-detail` | 五套液位站及环境/气体运行时节点细化。 |
| V23 | `v17-sensor-refinement` | 保留V17环形外观并规范液位站运行时命名。 |

未来版本应使用 `utility-tunnel-annular-vNN-<主题>`，其中 `NN` 比上一个已发布模型版本加一；不得把项目计划书、硬件清单或软件版本号拼入模型迭代号。同一自然日只发布并记录当天最终确认的最新一版，中间试验文件不占用正式版本号。
