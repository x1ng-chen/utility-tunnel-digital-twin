# 综合管廊实体样品模型

## 当前正式交付：V07（2026-09-02 当日最终版）

`utility-tunnel-annular-v07-final.blend` 与
`utility-tunnel-annular-v07-final.glb` 是当前唯一的正式工程模型。
它保留透明环形外壳、工业设备布局和 5 个液位站，并统一使用
`LEVEL-L01` 至 `LEVEL-L05` 及其探头、支架、线束、状态子节点；
`PIPE-G01`、`WATER-TRAY-01`、`FAN-01` 和 `GAS-01` 同样具备稳定名称。
V07 继承 V06 的完整顶盖与连续密封边，并清理历史重复布局层，将控制、液位、水路和燃气/通风功能区分离为可读的检修布局。

`asset-map-v07-final.json` 是 V07 的资产映射。`_TEMP` 表示实物接口尚未测量，
不得据此加工、接线或采购。

## 版本规则

- 每个自然日只保留当天最终确认的一版模型；同日中间 Blend、GLB、预览、映射和脚本不作为正式交付保留。
- 版本号按连续整数递增。V07 是 2026-09-02 的最终版，下一次正式发布从 V08 开始。
- V01—V04 是此前日期的基线；原 V05—V23 是 2026-08-31 的中间过程，已归并为当前 V05。完整过程仍可通过 Git 历史追溯。

| 版本 | 主题 | 主文件 |
|---|---|---|
| V01 | 环形概念基线 | `utility-tunnel-ring-v01.glb` |
| V02 | 环形验证基线 | `utility-tunnel-ring-v02.glb` |
| V03 | 矩形方案基线 | `utility-tunnel-rectangular-v03.glb` |
| V04 | 正式环形 Web 基线 | `utility-tunnel-annular-v04.glb` |
| V05 | 2026-08-31 最终环形实体与运行时节点 | `utility-tunnel-annular-v05-final.glb` |
| V06 | 2026-09-01 顶部与侧边完整封闭最终版 | `utility-tunnel-annular-v06-final.glb` |
| V07 | 2026-09-02 历史重叠层清理与功能区净空最终版 | `utility-tunnel-annular-v07-final.glb` |

## 功能与安全边界

- A 区包含检修门、环境测点、低压控制、网络、急停和报警；B 区包含独立水盘、5 个 FS-IR02 液位站、P-01 和 V-01；C 区包含 `PIPE-G01`、模拟漏点、气体/烟雾模块与风机。
- 水路与软管仅为设计/审查表达。P-01 保持干帽、V-01 保持锁闭；不接建筑给水、不通水、不通电。
- 探头螺纹、安装孔、线长、泵口、软管和风机电气参数均待实测，完成安全评审前不得进入实体加工或带电联调。
- 网页运行时文件须在完成模型压缩、资产映射切换和浏览器加载回归后，才可替换。

## 预览与验证

- `previews/utility-tunnel-annular-v07-final-hero.png`：V07 透明环形整体视图。
- `previews/utility-tunnel-annular-v07-final-clearance-inspection.png`：临时拆壳的功能区净空检查视图。
- `previews/utility-tunnel-annular-v07-final-top-closure.png`：继承顶盖与密封边检查视图。
- V07 映射明确为数字孪生/视觉模型；实体水电投运未获批准。
