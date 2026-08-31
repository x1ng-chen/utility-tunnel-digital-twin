# 环形综合管廊实体样品模型

## V18 加工与安全评审版

`utility-tunnel-annular-v18-fabrication-safety.blend` 是当前可编辑的工程源文件；
`utility-tunnel-annular-v18-fabrication-safety.glb` 是当前加工与安全评审用交付模型。
它约92MB，尚未替换 `frontend/public/models/utility-tunnel.glb` 的网页运行时副本；
需先完成减面/压缩、节点映射与浏览器加载回归。

模型以 `utility_tunnel_annular_v18_fabrication_safety.py` 为当前入口脚本；
它在保留的 V17 水路设计检查点上生成 V18。V14 是该迭代链的保留结构基线。
`asset-map-v18.json` 是V18评审用节点映射；网页运行时仍使用既有 `asset-map.json`，待模型压缩和加载回归后再切换。

### 连续模型版本链

模型版本只使用迭代号；项目计划书/硬件基线版本不再写入文件名。V11原有的
`v11-v35` 文件已规范为 `v11-hardware-baseline`，其中“hardware-baseline”是主题，
不是第二个版本号。

| 版本 | 主题 | 主文件 |
|---|---|---|
| V10 | 环形实体基线 | `utility-tunnel-annular-v10.glb` |
| V11 | 硬件基线 | `utility-tunnel-annular-v11-hardware-baseline.glb` |
| V12 | 分布式传感器 | `utility-tunnel-annular-v12-distributed-sensors.glb` |
| V13 | 环形站点 | `utility-tunnel-annular-v13-annular-stations.glb` |
| V14 | 加工细节 | `utility-tunnel-annular-v14-fabrication-detail.glb` |
| V15 | 液位/风机/水泵 | `utility-tunnel-annular-v15-level-fan-pump.glb` |
| V16 | 分散液位站 | `utility-tunnel-annular-v16-distributed-levels.glb` |
| V17 | 水路设计 | `utility-tunnel-annular-v17-fabrication-waterloop.glb` |
| V18 | 加工与安全评审 | `utility-tunnel-annular-v18-fabrication-safety.glb` |

### 功能分区和资产

- A 区：检修门、门磁、环境与温度测点、低压控制箱、网络、急停和报警。
- B 区：顶板滴水嘴、独立围边水盘、5个 FS-IR02 光学液位站、P-01水泵、V-01截止阀、补水歧管及溢流回水路径。
- C 区：密闭环形 `PIPE-G01`、可见 `LEAK-G01` 模拟漏点、CH4/CO/O2、
  烟雾、风机转速/电流反馈和顶部排风。
- 5个液位站分散为 L01低液位、L02常规、L03高、L04超高、L05泄漏位；每站保留FS-IR02板卡（约38.6×22.1mm）、外置探头、支架、XH2.54线束和编号。
- 两台12V四线轴流风机均按120×120mm表达，分别用于进气与排风；各自保留PWM/TACH线束标识。
- V18 将原先可能被误读为孔距的四角风机标记改为可调边夹；仅120mm外框尺寸可用，孔距、孔径、厚度、电流与PWM/TACH定义均要求实测。
- 5个FS-IR02探头改为无孔径假设的分体夹具与卡尺基准；待量取探头螺纹外径、螺母对边和线缆长度后才能确定钻孔。
- 新增IF-01干侧调理评审位、滴水回环、干湿隔板、P-01进/出水干帽及V-01关断锁定；它们表示安全评审状态，不构成已批准的原理图、接线或通水方案。

### 安全与流向

- 橙色 `PIPE-G01` 是密闭的燃气泄漏模拟对象，不向课堂释放或输送可燃、
  有毒气体。异常值由 `SIMBOX-01` 隔离信号模拟盒生成。
- 青色气路是独立的安全空气路径：防雨 `AIR-IN-01` → 过滤器 → 流量计 →
  低压抽气泵 → 止回阀 → 采样歧管/采样腔 → 顶部 `VENT-01`。它不与 G01 混接。
- V18保留V17待验证的低水量路径：水槽 → P-01 → V-01 → 补水歧管 → 溢流回水槽；当前P-01干帽、V-01锁闭。它不连接建筑给水，也不表示已通水/通电；实体投运前必须完成24V保险、水电隔离、软管/孔径实测和渗漏测试，并取得项目负责人批准。

### 预览

- `previews/utility-tunnel-annular-v18-fabrication-safety-hero.png`：整机外观、可调风机边夹与加工门槛。
- `previews/utility-tunnel-annular-v18-fabrication-safety-detail.png`：液位分体夹具、IF-01评审位、P-01干帽和V-01锁闭。

### 验证结果

V18 已检查5块FS-IR02板卡、5个外置探头、5个无孔径分体夹具、两台120mm风机、IF-01、P-01干帽、V-01锁夹和K-01模型节点存在；GLB可重新导入且关键节点齐全。探头螺纹孔径、风机孔距和水泵软管规格尚无可靠实物尺寸，不得直接用于加工。

### 历史归档

`utility-tunnel-ring-v01`、`utility-tunnel-ring-v02`、
`utility-tunnel-rectangular-v03` 与 `utility-tunnel-annular-v04` 保留为建模
演进证据，不作为网页运行时模型。对应的三视图、预览、资产映射和
`fabrication/utility-tunnel-ring-build-pack-v01.md` 用于追溯早期结构与
制作讨论；涉及尺寸、气路或部件配置时，以 V17 说明和最新项目安全边界为准。
