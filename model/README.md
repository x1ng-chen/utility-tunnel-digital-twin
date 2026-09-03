# 综合管廊实体样品模型

## 当前网页运行时基线：V07（2026-09-02）

`utility-tunnel-annular-v07-final.blend` 与
`utility-tunnel-annular-v07-final.glb` 是当前已验证的网页运行时工程模型。
它保留透明环形外壳、工业设备布局和 5 个分散液位站；五套 FS-IR02 分别固定在排水、吸水、泵入口、阀后和回水管段，
并各自具备板卡、探头、支架、管夹、线束和中文测点牌。`PIPE-G01`、`WATER-TRAY-01`、`FAN-01` 和 `GAS-01` 同样具备稳定名称。

`asset-map-v07-final.json` 是 V07 的资产映射，并已与 Web 当前 13 个运行资产契约对齐。
V07 的 GLB 已通过体积、节点完整性与浏览器回归门禁，可作为 Web 运行模型。
`_TEMP` 表示实物接口尚未测量，不得据此加工、接线或采购。

## V08 协同候选：控制区 BT-01 可选视觉模块

队友在远端提交了 V08 的 BT-01（HC-05 蓝牙模块）视觉设计、映射和质检资料。
`asset-map-v08-final.json` 与 `quality-report-v08-final.md` 已纳入仓库作为候选审查记录；
V08 的 LFS 二进制对象当前无法从远端下载（GitHub 返回 404），因此本地和网页继续使用已验证的 V07，
待补齐对象后再执行 V08 独立发布、回滚和浏览器门禁。BT-01 仅是可选近场调试的视觉表达，
不改变 ESP8266-01S 的正式无线链路，也不构成接线、供电或实体投运许可。

## 版本规则

- 每个自然日只保留当天最终确认的一版模型；同日中间 Blend、GLB、预览、映射和脚本不作为正式交付保留。
- 版本号按连续整数递增。V07 是当前网页运行时基线；V08 为候选模型资料，二进制对象恢复后才可升级为运行时正式版。
- V01—V04 是此前日期的基线；原 V05—V23 是 2026-08-31 的中间过程，已归并为当前 V05。完整过程仍可通过 Git 历史追溯。

| 版本 | 主题 | 主文件 |
|---|---|---|
| V01 | 环形概念基线 | `utility-tunnel-ring-v01.glb` |
| V02 | 环形验证基线 | `utility-tunnel-ring-v02.glb` |
| V03 | 矩形方案基线 | `utility-tunnel-rectangular-v03.glb` |
| V04 | 正式环形 Web 基线 | `utility-tunnel-annular-v04.glb` |
| V05 | 2026-08-31 最终环形实体与运行时节点 | `utility-tunnel-annular-v05-final.glb` |
| V06 | 2026-09-01 顶部与侧边完整封闭最终版 | `utility-tunnel-annular-v06-final.glb` |
| V07 | 2026-09-02 五个分散管路液位测点网页运行时版 | `utility-tunnel-annular-v07-final.glb` |
| V08 | 2026-09-03 控制区 BT-01 可选视觉模块候选版 | `utility-tunnel-annular-v08-final.glb` |

## 功能与安全边界

- A 区包含检修门、环境测点、低压控制、网络、急停和报警；B 区包含独立水盘、5 个 FS-IR02 液位站、P-01 和 V-01；C 区包含 `PIPE-G01`、模拟漏点、气体/烟雾模块与风机。
- 水路与软管仅为设计/审查表达。P-01 保持干帽、V-01 保持锁闭；不接建筑给水、不通水、不通电。
- 探头螺纹、安装孔、线长、泵口、软管和风机电气参数均待实测，完成安全评审前不得进入实体加工或带电联调。
- 网页只使用通过模型压缩、资产映射与浏览器加载门禁的 V07 GLB；后续版本必须重复同一门禁并具备可回滚对象后才可替换。

## 预览与验证

- `previews/utility-tunnel-annular-v07-final-hero.png`：V07 透明环形整体视图。
- `previews/utility-tunnel-annular-v07-final-clearance-inspection.png`：临时拆壳的功能区净空检查视图。
- `previews/utility-tunnel-annular-v07-final-top-closure.png`：继承顶盖与密封边检查视图。
- `previews/utility-tunnel-annular-v08-final-bt01-inspection.png`：V08 控制 PCB、BT-01 和相邻端子的近景审查视图（LFS 对象恢复后提供）。
- V07 映射明确为数字孪生/视觉模型；实体水电投运未获批准。
