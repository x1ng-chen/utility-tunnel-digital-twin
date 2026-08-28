# 环形综合管廊实体样品模型

## V04 环形演示版

`utility-tunnel-annular-v04.blend` 是当前展示和评审使用的 Blender 模型；
`utility-tunnel-annular-v04.glb` 是面向 Web 三维场景导入的轻量导出文件。

模型以 `utility_tunnel_annular_v04.py` 为入口脚本，并复用
`utility_tunnel_ring_v01.py` 中的环形舱体、透明亚克力壳体、顶盖和基础
资产结构。执行 V04 入口脚本会重新生成 `.blend`、`.glb` 与两张预览图。

### 功能分区和资产

- A 区：检修门、门磁、环境与温度测点、低压控制箱、网络、急停和报警。
- B 区：顶板滴水嘴、独立围边水盘、漏水探头、高液位浮球及手动放水口。
- C 区：密闭环形 `PIPE-G01`、可见 `LEAK-G01` 模拟漏点、CH4/CO/O2、
  烟雾、风机转速/电流反馈和顶部排风。

### 安全与流向

- 橙色 `PIPE-G01` 是密闭的燃气泄漏模拟对象，不向课堂释放或输送可燃、
  有毒气体。异常值由 `SIMBOX-01` 隔离信号模拟盒生成。
- 青色气路是独立的安全空气路径：`AIR-IN-01` → 采样腔 → `FAN-01` →
  顶部 `VENT-01`。它不与 G01 混接。
- 水路只允许少量清水：滴水嘴 → 接水盘 → 漏水/高液位测点 → 手动排空，
  不设置循环泵、电磁阀或建筑给水连接。

### 预览

- `previews/utility-tunnel-annular-v04-hero.png`：透明封闭外观。
- `previews/utility-tunnel-annular-v04-functional.png`：检修/功能剖视。

### 验证结果

V04 已检查 `PIPE-G01` 为闭合曲线；关键资产无缺失；GLB 已重新导入验证，
文件约 8.5 MB。
