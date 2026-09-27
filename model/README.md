# 综合管廊实体样品模型

## 当前网页运行时：用户提供的 V13 导出（2026-09-26）

`frontend/public/models/utility-tunnel.glb` 已使用用户提供的 V13 导出，SHA-256 为
`a89b5d09ea26c5db5c17acb72ac920fd9dd37697e009525fa0d81fc442dc8dab`，包含 829 个节点。
`model/v13-runtime-handoff.json` 记录同源导出与回退哈希；
`frontend/src/services/v13AssetBindings.json` 保留旧台账中能确认的节点映射；
前端另外按型号和编号将台架 31 路传感器绑定到各自的 V13 节点。
V13 中可见的 `LEVEL-L05` 是模型视觉站位，实物已拆除，不绑定现场活动告警。
`frontend/public/models/utility-tunnel-v07.glb` 保留为旧版回退文件。

## 最新审查归档：V11（2026-09-09，进行中）

今日气泵装配及液位检测端/空心接口成果归档为 `utility-tunnel-annular-v11-candidate.blend` / `.glb`。
该历史候选仍有 L01 阀体冲突、其他传感器支撑和标签问题，当时未替换 V07 网页运行基线，不可直接加工。
范围、复现与证据见 [V11 审查报告](quality-report-v11-candidate.md)。V10 历史归档不变。

## 历史网页运行时基线：V07（2026-09-02）

`utility-tunnel-annular-v07-final.blend` 与
`utility-tunnel-annular-v07-final.glb` 是此前已验证的网页运行时工程模型，现保留为回退版本。
它保留透明环形外壳、工业设备布局和 5 个分散液位站；五套 FS-IR02 分别标为排水、吸水、泵入口、阀后和回水管段，
并各自具备板卡、探头、支架、管夹、线束和中文测点牌。`PIPE-G01`、`WATER-TRAY-01`、`FAN-01` 和 `GAS-01` 同样具备稳定名称。

`asset-map-v07-final.json` 是 V07 的归档映射；2026-09-07 台账新增五个独立液位测点后，门禁验证 V07 仍能绑定全部 18 个资产。
节点存在不等于物理连接已验收：本轮审查发现旧版吸水/回水连接表达不足，修复另存 V09 候选，不回写历史模型。
V07 的 GLB 已通过体积、节点完整性与浏览器回归门禁，可作为 Web 运行模型。
`_TEMP` 表示实物接口尚未测量，不得据此加工、接线或采购。

## V08 协同候选：控制区 BT-01 可选视觉模块

队友在远端提交了 V08 的 BT-01（HC-05 蓝牙模块）视觉设计、映射和质检资料。
`asset-map-v08-final.json` 与 `quality-report-v08-final.md` 已纳入仓库作为候选审查记录；
V08 的 LFS 对象已于 2026-09-07 补传并通过独立缓存下载核验；9 月 3—4 日的 404 是历史状态。
本轮审查发现 145 个非 V07/BT 基线的历史节点混入和 BT-01 安装间隔，故不直接升级 V08。
当时网页继续使用 V07，修复成果另存 V09 候选。BT-01 仅是可选近场调试的视觉表达，
不改变 ESP8266-01S 的正式无线链路，也不构成接线、供电或实体投运许可。

## 版本规则

- 每个自然日只保留当天最终确认的一版模型；同日中间 Blend、GLB、预览、映射和脚本不作为正式交付保留。
- 版本号按连续整数递增。V07 是历史网页运行时基线；V08、V09 为历史候选；当前网页使用用户提供的 V13 导出。
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
| V09 | 2026-09-07 受控导出、测点连接和铭牌修复候选 | `utility-tunnel-annular-v09-candidate.glb` |

## V09 可重复验证

- 构建：`blender -b --python tools/build_model_v09.py -- <仓库绝对路径>`（Blender 5.2.1、微软雅黑字体）。独立进程导入已归档 V08，不覆盖正在编辑的场景。
- 结构门禁：`node --test tools/glb-contract.test.mjs tools/model-gate.test.mjs` 与 `node tools/check-twin-model-artifacts.mjs --require-candidate`；包完整性：`node tools/model-package.mjs`。
- 映射：`asset-map-v09-candidate.json`；结构审查：`v09-structural-audit.json`；验收范围：`quality-report-v09-candidate.md`。
- 预览：`previews/v09-overview.png`、`v09-front.png`、`v09-top.png`、`v09-water.png`、`v09-control.png`。检查图暂隐外壳和顶盖，GLB 保留这些对象。
- 候选不等于投运。不得凭新增管路表达启用循环泵、受控阀或改变已批准的干燥管廊/少量积水演示边界。

## 功能与安全边界

- A 区包含检修门、环境测点、低压控制、网络、急停和报警；B 区包含独立水盘、5 个 FS-IR02 液位站、P-01 和 V-01；C 区包含 `PIPE-G01`、模拟漏点、气体/烟雾模块与风机。
- 水路与软管仅为设计/审查表达。P-01 保持干帽、V-01 保持锁闭；不接建筑给水、不通水、不通电。
- 探头螺纹、安装孔、线长、泵口、软管和风机电气参数均待实测，完成安全评审前不得进入实体加工或带电联调。
- 网页模型更新须通过体积、资产映射与浏览器加载门禁，并保留可回滚对象；当前 V13 导出与 V07 回退文件均已保留。

## V13 温湿度实物对应关系

当前只安装四只温湿度传感器，实物编号不改变：SHT-01→模型 SHT30-01，SHT-02→SHT30-02，SHT-03→SHT30-04，SHT-04→SHT30-05。模型中间的 SHT30-03 无实物，网页运行时隐藏该站的部件，不绑定数据或报警。其他传感器不因温湿度的空位顺延；氧气位置另见下节。

## V13 氧气实物对应关系

三只氧传感器的实物编号与接线保持 O2-01、O2-02、O2-03，网页位置依次为模型 ME2O2-01、ME2O2-03、ME2O2-05。模型 ME2O2-02 与 ME2O2-04 没有实物，网页运行时隐藏其部件，不绑定实时数据或报警。氧气测量尚未标定，继续只显示原始遥测。

## 预览与验证

- `previews/utility-tunnel-annular-v07-final-hero.png`：V07 透明环形整体视图。
- `previews/utility-tunnel-annular-v07-final-clearance-inspection.png`：临时拆壳的功能区净空检查视图。
- `previews/utility-tunnel-annular-v07-final-top-closure.png`：继承顶盖与密封边检查视图。
- `previews/utility-tunnel-annular-v08-final-bt01-inspection.png`：V08 控制 PCB、BT-01 和相邻端子的近景审查视图（LFS 对象恢复后提供）。
- V07 映射明确为数字孪生/视觉模型；实体水电投运未获批准。
