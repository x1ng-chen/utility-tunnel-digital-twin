# 环形综合管廊实体样品模型

## V10 环形实体迭代版

`utility-tunnel-annular-v10.blend` 是当前展示和评审使用的 Blender 模型；
`utility-tunnel-annular-v10.glb` 是面向 Web 三维场景导入的轻量导出文件。
网页运行时副本为 `frontend/public/models/utility-tunnel.glb`，由同一源模型
生成，符合项目《三维实体模型接入规范》的默认路径约定。

模型以 `utility_tunnel_annular_v10.py` 为当前入口脚本，按 V05—V10 的
可复现迭代链复用环形舱体、透明亚克力壳体、顶盖和基础资产结构。V04 作为
已归档基线保留；执行 V10 入口脚本会重新生成当前 `.blend`、`.glb` 与预览图。

### 功能分区和资产

- A 区：检修门、门磁、环境与温度测点、低压控制箱、网络、急停和报警。
- B 区：顶板滴水嘴、独立围边水盘、漏水探头、高液位浮球及手动放水口。
- C 区：密闭环形 `PIPE-G01`、可见 `LEAK-G01` 模拟漏点、CH4/CO/O2、
  烟雾、风机转速/电流反馈和顶部排风。
- A 区补充透明检修门、PCB、12 V 电源、保险、继电器导轨与线槽固定；B 区
  补充独立内胆、50 mL 水位线、液位视窗和手动排水阀；C 区补充防雨进气罩、
  过滤器、流量计、抽气泵、止回阀、三路取样快接头及回气接口。

### 安全与流向

- 橙色 `PIPE-G01` 是密闭的燃气泄漏模拟对象，不向课堂释放或输送可燃、
  有毒气体。异常值由 `SIMBOX-01` 隔离信号模拟盒生成。
- 青色气路是独立的安全空气路径：防雨 `AIR-IN-01` → 过滤器 → 流量计 →
  低压抽气泵 → 止回阀 → 采样歧管/采样腔 → 顶部 `VENT-01`。它不与 G01 混接。
- 水路只允许少量清水：滴水嘴 → 接水盘 → 漏水/高液位测点 → 手动排空，
  不设置循环泵、电磁阀或建筑给水连接。

### 预览

- `previews/utility-tunnel-annular-v10-hero.png`：透明封闭外观。
- `previews/utility-tunnel-annular-v10-functional.png`：检修/功能剖视。
- `previews/utility-tunnel-annular-v10-control-detail.png`：A 区低压控制箱细节。
- `previews/utility-tunnel-annular-v09-water-detail.png`：B 区独立水槽细节。

### 验证结果

V10 已检查 `PIPE-G01` 为闭合曲线；关键资产无缺失；GLB 已重新导入验证，
整体尺寸为 `1000 × 500 × 420 mm`，最低点为 `Z=0`，文件约 3.8 MB、
约 84,608 三角面。
