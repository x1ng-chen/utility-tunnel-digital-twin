# 综合管廊实体样品模型

## 当前设计最终版：V13（2026-09-14）

用户已确认当前 V13 为项目数字孪生模型的设计最终版。归档文件为 `utility-tunnel-annular-v13-candidate.blend` / `.glb`，文件名保留上传时的不可变标识；模型状态以本索引和项目实施日志为准。V13 设计定版不表示实体加工、通水通气通电或项目最终验收通过。原归档 GLB 保留历史记录；前端运行文件已从该 BLEND 单独重导出，详见下文。

## 当前前端三维模型：V13（2026-09-26）

`frontend/public/models/utility-tunnel.glb` 从用户提供、与仓库归档 SHA256 相同的 V13 BLEND 导出。Blender 5.2.2 仅导出当前可见且参与渲染的 829 个网格；72 个有意隐藏的围护和屋面部件未导出。运行 GLB 有 829 个唯一命名网格，五个 `LEVEL-L01-探头` 至 `LEVEL-L05-探头` 均可分别绑定和定位。源文件与运行文件的哈希、命令及节点清单在 `v13-runtime-handoff.json`，导出脚本为 `tools/export_v13_runtime.py`。

网页默认加载 V13；可切换到此前已启用的模型版本，静态 V07 回退文件是 `frontend/public/models/utility-tunnel-v07.glb`。前端的 `frontend/src/services/v13AssetBindings.json` 明确列出 12 个可确认的资产节点，包括 5 个独立液位探头。`FAN-02` 以四线排风机上框作为定位和交互锚点。旧台账的 `SEEP-W01`、`MOIST-01`、`ENV-01`、`GAS-01`、`VIB-01`、`FAN-01`、`PCB-01` 在 V13 中没有可确认的同一实物节点：浮球不等于旧水位传感器，SHT30 不等于 DHT11，气体管路不等于复合监测节点，四线风机也不等于旧双路驱动小风扇。未绑定资产明确显示为缺失映射，不在新模型中生成伪造定位点。模型替换属于网页可视化，不改变实体接口和安全验收状态。

## 前一审查归档：V12（2026-09-10，重建进行中）

`utility-tunnel-annular-v12-candidate.blend` / `.glb` 为按计划数量从零重建的分散布设候选。两台泵尚未按当天新提供的实物照片修正，全场标注、围护、管路与装配验证未通过，不替换网页V07。详见 [V12审查报告](quality-report-v12-candidate.md) 和 [泵实物确认](pump-reference-2026-09-10.md)。

## 前一审查归档：V11（2026-09-09，进行中）

今日气泵装配及液位检测端/空心接口成果归档为 `utility-tunnel-annular-v11-candidate.blend` / `.glb`。
该候选仍有 L01 阀体冲突、其他传感器支撑和标签问题，不替换 V07 网页运行基线，不可直接加工。
范围、复现与证据见 [V11 审查报告](quality-report-v11-candidate.md)。V10 历史归档不变。

## 前一已验证网页模型：V07（2026-09-02）

`utility-tunnel-annular-v07-final.blend` 与
`utility-tunnel-annular-v07-final.glb` 是前一已验证的网页运行时工程模型。
它保留透明环形外壳、工业设备布局和 5 个分散液位站；五套 FS-IR02 分别标为排水、吸水、泵入口、阀后和回水管段，
并各自具备板卡、探头、支架、管夹、线束和中文测点牌。`PIPE-G01`、`WATER-TRAY-01`、`FAN-01` 和 `GAS-01` 同样具备稳定名称。

`asset-map-v07-final.json` 是 V07 的归档映射；2026-09-07 台账新增五个独立液位测点后，门禁验证 V07 仍能绑定全部 18 个资产。
节点存在不等于物理连接已验收：本轮审查发现旧版吸水/回水连接表达不足，修复另存 V09 候选，不回写历史模型。
V07 的 GLB 已通过体积、节点完整性与浏览器回归门禁，可作为回退模型。
`_TEMP` 表示实物接口尚未测量，不得据此加工、接线或采购。

## V08 协同候选：控制区 BT-01 可选视觉模块

队友在远端提交了 V08 的 BT-01（HC-05 蓝牙模块）视觉设计、映射和质检资料。
`asset-map-v08-final.json` 与 `quality-report-v08-final.md` 已纳入仓库作为候选审查记录；
V08 的 LFS 对象已于 2026-09-07 补传并通过独立缓存下载核验；9 月 3—4 日的 404 是历史状态。
本轮审查发现 145 个非 V07/BT 基线的历史节点混入和 BT-01 安装间隔，故不直接升级 V08。
网页继续使用 V07，修复成果另存 V09 候选。BT-01 仅是可选近场调试的视觉表达，
不改变 ESP8266-01S 的正式无线链路，也不构成接线、供电或实体投运许可。

## 版本规则

- 每个自然日只保留当天最终确认的一版模型；同日中间 Blend、GLB、预览、映射和脚本不作为正式交付保留。
- 版本号按连续整数递增。V13 是当前前端可视化模型，V07 保留为已验证的回退版本；V08、V09 是历史候选。
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
| V13 | 2026-09-14 用户确认的设计最终版 | `utility-tunnel-annular-v13-candidate.glb` |

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
- 网页默认使用从 V13 BLEND 重导出的 GLB，并保留 V07 回退对象；五个液位探头通过节点和浏览器定位门禁，其他未映射资产继续标明缺失。

## 预览与验证

- `previews/utility-tunnel-annular-v07-final-hero.png`：V07 透明环形整体视图。
- `previews/utility-tunnel-annular-v07-final-clearance-inspection.png`：临时拆壳的功能区净空检查视图。
- `previews/utility-tunnel-annular-v07-final-top-closure.png`：继承顶盖与密封边检查视图。
- `previews/utility-tunnel-annular-v08-final-bt01-inspection.png`：V08 控制 PCB、BT-01 和相邻端子的近景审查视图（LFS 对象恢复后提供）。
- V07 映射明确为数字孪生/视觉模型；实体水电投运未获批准。
