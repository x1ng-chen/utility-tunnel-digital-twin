# V11 审查候选：2026-09-09

状态：进行中，非生产发布，非实体加工图。此为今日唯一归档候选，未通过整体验收。

## 完成范围

- 气泵七个附件归位，螺钉补齐连接。
- 五个液位检测头改向管道侧，补齐检测芯杆。
- 三条水路重建内外壁，五个连接座/管夹开孔，L02—L05 加工侧孔。
- GLB 重新导入后，13 个本轮开孔对象检查结果均为零开边、零非流形边、零面积退化面；五个芯杆与壳体连接；地板检查通过。
- 已逐图查看五个测点剖面，最终管路重建后复看 L02—L05。

## 尚未完成

- L01 光学端与排水阀体、活接冲突，需独立测量接头；不能直接加工阀体。
- 气体采样盒、氧气立柱、烟雾/甲烷面板和环境模块仍有支撑或穿插问题。
- 中文标签拥挤、整体净空、管内贯通、壁厚、密封、实物孔距与尺寸未整体验收。
- 网格检查通过不等于水力连通或制造认证；V07 网页运行基线不变，不授权通水/通电。

## 文件与复现

- 主模型：`utility-tunnel-annular-v11-candidate.blend` / `.glb`。
- 检查：`v11-bore-review.json`、`v11-whole-scene-audit.json`、`v11-air-pump-review.json`。
- 截图：`previews/v11-L01-section.png` 至 `v11-L05-section.png`，以及气泵前后对比。
- `sources/2026-09-08-iteration-input.blend` 是保留的昨日输入快照，不是另一份今日交付模型；不得覆盖 Git 已归档 V10。
- 使用 Blender 5.2.1，依次执行 `tools/refine_air_pump.py`、`tools/refine_level_optics.py`、`tools/refine_level_bores.py`、`tools/audit_level_bore_trial.py`，每条命令形式为 `blender -b --python <脚本> -- <仓库根目录>`。输出均进入本地 `_qa_iteration_20260909`，不会覆盖归档文件。
- 光学端及开孔阶段都是同一 V11 的构建步骤，不作为额外正式版本。
- 本包哈希与资产节点验证记录见 `v11-upload-manifest.json`。

参与人：史润佳。实际工时未提供，不估填。没有证据支持将其他成员今日工作记为已完成。
