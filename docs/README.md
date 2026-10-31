# 文档导航

当前入口：[项目主页](../README.md) · [当前进度](PROJECT_STATUS.md) · [2026-10-31发布验证](releases/2026-10-31/README.md)。

## 按任务阅读

| 任务 | 文档 |
| --- | --- |
| 启动软件演示 | [Windows/Docker](../deploy/agent-demo/README.md) |
| 实物数据接入 | [只读联调](../deploy/hardware-live/README.md) |
| 三Agent、RAG与仿真闭环 | [软件冲刺](software-sprint-20261027/README.md) |
| 设备证据护栏与经验审核 | [护栏、联合评测、受控经验](guardrails-experience-20261027/README.md) |
| 可续查排障与本地决策 | [Agent能力](agent-capabilities-20261029/README.md) |
| 软件演示验收与真实模型边界 | [软件交付](software-release-20261029/README.md) |
| 四板、网关完整固件 | [发布说明](../firmware/four-controller/RELEASE.md) |
| 接线、引脚、485 | [四主控接线冻结](hardware/four-controller-wiring-20261026/README.md) |
| 风机/继电器/INA226 | [接线](hardware/fan-relay-ina226-wiring-20261029.md) · [台架记录](hardware/fan-bench-20261029.md) |
| 板2温湿度问题 | [完整排查记录](hardware/ctrl02-sht-diagnosis-20261029.md) |
| 火焰实物确认 | [五路用户验收](hardware/flame-five-user-acceptance-20261029.md) |
| 31路模型映射与报警 | [统一映射](hardware/sensor-numbering-unified-20261029.md) · [规则](hardware/sensor-alarm-rules-20261029.md) |
| 当前与历史模型 | [模型导航](../model/README.md) |
| 软件贡献 | [协作规范](../CONTRIBUTING.md) |

## 文档优先级

1. `PROJECT_STATUS.md`记录当前结论和未完成事项。
2. 当前版本的身份/接线/模型清单用于实施；历史清单仅作迁移依据。
3. 日期化验收记录证明当时、指定范围内的结果；测试通过不代替实物测量。
4. 历史计划、旧README和V16/V17等交付保留，不自动改写为当前状态。

[旧主页归档](history/README-before-20261031.md)。遇到冲突请记录设备、版本和证据出处，再更新当前入口；不得删除失败记录来制造“全部通过”。
