# 环形综合管廊实体样品模型

## V17 液位监测与水路建模版

`utility-tunnel-annular-v17-fabrication-waterloop.blend` 是当前可编辑的工程源文件；
`utility-tunnel-annular-v17-fabrication-waterloop.glb` 是当前评审用交付模型。
它约65MB，尚未替换 `frontend/public/models/utility-tunnel.glb` 的网页运行时副本；
需先完成减面/压缩、节点映射与浏览器加载回归。

模型以 `utility_tunnel_annular_v17_fabrication_waterloop.py` 为当前入口脚本；
它以 V16 分散液位站检查点为基础生成 V17。V14 是该迭代链的保留结构基线。
`asset-map-v17.json` 是V17评审用节点映射；网页运行时仍使用既有 `asset-map.json`，待模型压缩和加载回归后再切换。

### 功能分区和资产

- A 区：检修门、门磁、环境与温度测点、低压控制箱、网络、急停和报警。
- B 区：顶板滴水嘴、独立围边水盘、5个 FS-IR02 光学液位站、P-01水泵、V-01截止阀、补水歧管及溢流回水路径。
- C 区：密闭环形 `PIPE-G01`、可见 `LEAK-G01` 模拟漏点、CH4/CO/O2、
  烟雾、风机转速/电流反馈和顶部排风。
- 5个液位站分散为 L01低液位、L02常规、L03高、L04超高、L05泄漏位；每站保留FS-IR02板卡（约38.6×22.1mm）、外置探头、支架、XH2.54线束和编号。
- 两台12V四线轴流风机均按120×120mm表达，分别用于进气与排风；各自保留PWM/TACH线束标识。

### 安全与流向

- 橙色 `PIPE-G01` 是密闭的燃气泄漏模拟对象，不向课堂释放或输送可燃、
  有毒气体。异常值由 `SIMBOX-01` 隔离信号模拟盒生成。
- 青色气路是独立的安全空气路径：防雨 `AIR-IN-01` → 过滤器 → 流量计 →
  低压抽气泵 → 止回阀 → 采样歧管/采样腔 → 顶部 `VENT-01`。它不与 G01 混接。
- V17水路为待验证的低水量设计：水槽 → P-01 → V-01 → 补水歧管 → 溢流回水槽。它不连接建筑给水，也不表示已通水/通电；实体投运前必须完成24V保险、水电隔离、软管/孔径实测和渗漏测试。

### 预览

- `previews/utility-tunnel-annular-v17-fabrication-waterloop-hero.png`：整机外观及120mm风机。
- `previews/utility-tunnel-annular-v17-fabrication-waterloop-levels.png`：液位站、水泵、阀门及水路细节。

### 验证结果

V17 已检查5块FS-IR02板卡、5个外置探头、5个探头支架、两台120mm风机、P-01、V-01和K-01继电器控制件存在；GLB 头部及声明长度有效。探头螺纹孔径与水泵软管规格尚无可靠实物尺寸，不得直接用于加工。

### 历史归档

`utility-tunnel-ring-v01`、`utility-tunnel-ring-v02`、
`utility-tunnel-rectangular-v03` 与 `utility-tunnel-annular-v04` 保留为建模
演进证据，不作为网页运行时模型。对应的三视图、预览、资产映射和
`fabrication/utility-tunnel-ring-build-pack-v01.md` 用于追溯早期结构与
制作讨论；涉及尺寸、气路或部件配置时，以 V17 说明和最新项目安全边界为准。
