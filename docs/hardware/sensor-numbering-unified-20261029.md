# 31路传感器同编号映射（2026-10-29）

当前版本：`v24-unified-numbering-20261029.1`。已安装在独立实物联调环境；映射和实物验收分别记录。

| 采集资产编码 | 物理／模型显示编号 | 工位 | 主控 | 模型对象 |
|---|---|---|---|---|
| SMOKE-01 | MQ2-01 | P1 | CTRL-04 | SMOKE-01 |
| GAS-CH4-01 | MQ4-01 | P1 | CTRL-04 | GAS-CH4-01 |
| GAS-CO-01 | CO-01 | P1 | CTRL-04 | GAS-CO-01 |
| FLAME-01 | FLAME-01 | P1 | CTRL-04 | FLAME-01 |
| MQ2-02 | MQ2-02 | P2 | CTRL-03 | MQ2-02 |
| MQ4-02 | MQ4-02 | P2 | CTRL-03 | MQ4-02 |
| CO-02 | CO-02 | P2 | CTRL-03 | CO-02 |
| FLAME-02 | FLAME-02 | P2 | CTRL-03 | FLAME-02 |
| MQ2-03 | MQ2-03 | P3 | CTRL-01 | MQ2-03 |
| MQ4-03 | MQ4-03 | P3 | CTRL-01 | MQ4-03 |
| CO-03 | CO-03 | P3 | CTRL-01 | CO-03 |
| FLAME-03 | FLAME-03 | P3 | CTRL-01 | FLAME-03 |
| MQ2-04 | MQ2-04 | P4 | CTRL-02 | MQ2-04 |
| MQ4-04 | MQ4-04 | P4 | CTRL-02 | MQ4-04 |
| CO-04 | CO-04 | P4 | CTRL-02 | CO-04 |
| FLAME-04 | FLAME-04 | P4 | CTRL-02 | FLAME-04 |
| MQ2-05 | MQ2-05 | P5 | CTRL-01 | MQ2-05 |
| MQ4-05 | MQ4-05 | P5 | CTRL-01 | MQ4-05 |
| CO-05 | CO-05 | P5 | CTRL-01 | CO-05 |
| FLAME-05 | FLAME-05 | P5 | CTRL-01 | FLAME-05 |
| LEVEL-L01 | LEVEL-01 | P4 | CTRL-04 | MESH_V12-FSIR02_L01_BOARD |
| ENV-01 | SHT-01 | P4 | CTRL-04 | ENV-01 |
| LEVEL-L02 | LEVEL-02 | P1 | CTRL-03 | MESH_V12-FSIR02_L02_BOARD |
| ENV-02 | SHT-02 | P1 | CTRL-03 | ENV-02 |
| LEVEL-L03 | LEVEL-03 | P3 | CTRL-01 | MESH_V12-FSIR02_L03_BOARD |
| ENV-03 | SHT-03 | P3 | CTRL-01 | ENV-03 |
| LEVEL-L04 | LEVEL-04 | P2 | CTRL-02 | MESH_V12-FSIR02_L04_BOARD |
| ENV-04 | SHT-04 | P2 | CTRL-02 | ENV-04 |
| GAS-O2-01 | O2-01 | P1 | CTRL-04 | GAS-O2-01 |
| GAS-O2-02 | O2-02 | P2 | CTRL-01 | GAS-O2-02 |
| GAS-O2-03 | O2-03 | P5 | CTRL-02 | GAS-O2-03 |

五路火焰已有用户实测通过；中央MQ2-05已核实告警551触发及恢复并获用户确认。新版本保持这些对象的位置和映射不变。
其他通道的正确性仍需各自实物验收；软件核验不等于传感器标定。

验证：后台34项、前端38项针对性测试及类型检查通过；实际Three.js核验755节点、31个唯一传感器绑定及双风机结构。
实物接口8秒窗口确认四板心跳和观测递增、实际提供的新GLB散列及31路工位映射一致。
同一窗口ENV-02/ENV-04存在观测过期，三路氧气质量异常，另行排查，未记为实物正常。

安装前数据库备份及迁移审计保存在私有 `.hardware-live/`；固件和MQTT设备身份未改。
