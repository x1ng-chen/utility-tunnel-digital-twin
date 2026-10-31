# 五个采集节点编号调整 V20

2026-10-28，依据用户最新带红色标号的模型截图，通过 Blender MCP 修改。

以四个业务管口所在侧为前方（Blender -X），图中左侧为 +Y：

| 图中位置 | 新节点号 | Blender 中心 x,y/mm |
| --- | --- | --- |
| 后左 | P1 | 440,540 |
| 后右 | P2 | 440,160 |
| 前左 | P3 | 260,540 |
| 前右 | P4 | 260,160 |
| 中央 | P5 | 350,350 |

节点标牌统一显示“P编号 / 采集节点”。模型分组 `STATION_P1`～`STATION_P5`、节点台面/支柱名称、节点属性及绑定表中的站点引用已一并同步，避免显示号与模型分组不一致。

本轮没有移动任何对象。V19 中的四块 STM32 主控位置保留；31 个传感器的坐标、独立资产编号、实物标签和既有主控归属均保留。截图只定义节点编号，本轮没有重新分配接线关系。旧标牌上的主控文字来自中断前草稿，本版节点标牌只显示本次明确指定的节点号。

- `square-five-station-v20-node-numbering.blend`：可编辑原生模型。
- `square-five-station-v20-node-numbering.glb`：完整模型导出，693 个节点，保留两台独立风机叶轮。
- `previews/node-numbering.png`：与标号图同方向的核对预览。
- `asset-map.json`、`sensor-bindings.json`、`station-focus.json`：本版模型映射。
- `node-numbering-review.json`：旧节点号到新节点号的迁移表、空间位置、四设备成员及不变项核对记录。
- `export-numbering-verification.json`：实际加载 GLB 的分组、绑定及位置核对。
- `renumber_nodes.py`、`render_reference.py`：本轮 MCP 执行脚本；输入为 V19，V19 原文件保留。

此次更新仅在本地模型完成，未写入平台数据库或切换网页运行模型。
