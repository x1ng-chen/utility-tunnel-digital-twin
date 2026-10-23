# 仓库清理记录（2026-10-23）

本次按项目负责人要求，清理主线中过期且未被当前运行、构建和质量门禁使用的内容。仅删除已合入主线的分支；保留所有未合并成果、台架/Agent 功能分支和开放 PR 的分支。

清理前主线：[`529f8c0`](https://github.com/x1ng-chen/utility-tunnel-digital-twin/commit/529f8c03e0af2e02f7ab26b827d0af43bc638b0a)。历史内容仍可通过以下固定提交链接获取，未改写 Git 历史。

主线共移除 69 个文件，原树中 Git blob 合计 116,054,784 字节（约 110.7 MiB）。这表示当前检出树减少的内容，不代表 Git 历史或 GitHub/LFS 配额即时减少。

## 保留边界

- 保留 V3.8 计划书、项目当前状态、验收记录、实施日志和部署说明。
- 保留 Vue/Django、STM32/ESP、IoTDA 网关、本地 MQTT、测试及部署配置。
- 保留 V06：V07 重建脚本仍引用它；保留 V07 回退、V08/V09 构建/门禁及 V10–V13 模型。
- 仅删除早期概念模型及其配套旧脚本；不改变当前网页运行 GLB、资产绑定与模型合同。
- 当前台架分支、AI Agent 分支、PR #29/#31 及其他有独有提交的 WIP/快照分支保留。

## 分支清理

下列分支均已验证其尖端提交为清理前 main 的祖先，且没有开放 PR 使用它们作为源分支。删除的是远端分支名，提交仍由主线历史保留。

| 分支 | 删除前提交 |
| --- | --- |
| `chore/hardware-bench-baseline-20260831` | [`af4fcc3`](https://github.com/x1ng-chen/utility-tunnel-digital-twin/commit/af4fcc3a28fcdda064b7b5aea6908dbf9a6beb24) |
| `codex/model-release-readiness` | [`fa9e70c`](https://github.com/x1ng-chen/utility-tunnel-digital-twin/commit/fa9e70cc45c258114f3868298fdd48659f6cbd40) |
| `docs/add-v3.2-plan` | [`63e63a1`](https://github.com/x1ng-chen/utility-tunnel-digital-twin/commit/63e63a1c0c0e4a0216486743ba725e8a57484820) |
| `docs/sync-current-project-20260928` | [`7c5467a`](https://github.com/x1ng-chen/utility-tunnel-digital-twin/commit/7c5467ae502fae24b695da1d956bd60797e1a89c) |
| `docs/sync-project-status-20260829` | [`91aae9a`](https://github.com/x1ng-chen/utility-tunnel-digital-twin/commit/91aae9abb42d4cdd862307979f0e396ae2ac5322) |
| `feature/model-annular-v04` | [`719bcea`](https://github.com/x1ng-chen/utility-tunnel-digital-twin/commit/719bcea7e4bb9268f3c8f4e3481f2b78ddf129ab) |
| `缺陷` | [`529f8c0`](https://github.com/x1ng-chen/utility-tunnel-digital-twin/commit/529f8c03e0af2e02f7ab26b827d0af43bc638b0a) |

需要恢复时，可从对应提交重新创建原分支；无需恢复或覆盖其他分支。

## 本次验证

- 已核对保留源码和配置未引用被删除的运行依赖；97 处固定提交历史链接的目标均存在。
- 仓库质量扫描：329 个文本文件通过；部署护栏 37 项、PostgreSQL 权限规则 27 项通过。
- 现有 GLB 合同与模型门禁测试：14/14 通过。
- 主线运行模型检查通过，19/19 资产节点可定位；运行 GLB 及 V3.8/V06–V13 关键保留文件的 Git blob 未改变。
- V09 的 LFS 二进制未在本次独立检出下载，普通门禁按既有逻辑跳过其二进制检查；本次未重跑严格候选包验收、全量浏览器或实物测试。
- `git diff --check` 通过。没有改写历史、清理 LFS 服务端对象或调整开放 PR。

## 移除文件及历史入口

### 已被 V3.8 替代的计划书（19 个）

- [docs/综合管廊数字孪生实体样品项目计划书_V1.3.docx](https://github.com/x1ng-chen/utility-tunnel-digital-twin/blob/529f8c03e0af2e02f7ab26b827d0af43bc638b0a/docs/%E7%BB%BC%E5%90%88%E7%AE%A1%E5%BB%8A%E6%95%B0%E5%AD%97%E5%AD%AA%E7%94%9F%E5%AE%9E%E4%BD%93%E6%A0%B7%E5%93%81%E9%A1%B9%E7%9B%AE%E8%AE%A1%E5%88%92%E4%B9%A6_V1.3.docx)
- [docs/综合管廊数字孪生运维实体样品项目计划书_V2.0.docx](https://github.com/x1ng-chen/utility-tunnel-digital-twin/blob/529f8c03e0af2e02f7ab26b827d0af43bc638b0a/docs/%E7%BB%BC%E5%90%88%E7%AE%A1%E5%BB%8A%E6%95%B0%E5%AD%97%E5%AD%AA%E7%94%9F%E8%BF%90%E7%BB%B4%E5%AE%9E%E4%BD%93%E6%A0%B7%E5%93%81%E9%A1%B9%E7%9B%AE%E8%AE%A1%E5%88%92%E4%B9%A6_V2.0.docx)
- [docs/综合管廊数字孪生运维实体样品项目计划书_V2.1.docx](https://github.com/x1ng-chen/utility-tunnel-digital-twin/blob/529f8c03e0af2e02f7ab26b827d0af43bc638b0a/docs/%E7%BB%BC%E5%90%88%E7%AE%A1%E5%BB%8A%E6%95%B0%E5%AD%97%E5%AD%AA%E7%94%9F%E8%BF%90%E7%BB%B4%E5%AE%9E%E4%BD%93%E6%A0%B7%E5%93%81%E9%A1%B9%E7%9B%AE%E8%AE%A1%E5%88%92%E4%B9%A6_V2.1.docx)
- [docs/综合管廊数字孪生运维实体样品项目计划书_V2.2.docx](https://github.com/x1ng-chen/utility-tunnel-digital-twin/blob/529f8c03e0af2e02f7ab26b827d0af43bc638b0a/docs/%E7%BB%BC%E5%90%88%E7%AE%A1%E5%BB%8A%E6%95%B0%E5%AD%97%E5%AD%AA%E7%94%9F%E8%BF%90%E7%BB%B4%E5%AE%9E%E4%BD%93%E6%A0%B7%E5%93%81%E9%A1%B9%E7%9B%AE%E8%AE%A1%E5%88%92%E4%B9%A6_V2.2.docx)
- [docs/综合管廊数字孪生运维实体样品项目计划书_V2.3.docx](https://github.com/x1ng-chen/utility-tunnel-digital-twin/blob/529f8c03e0af2e02f7ab26b827d0af43bc638b0a/docs/%E7%BB%BC%E5%90%88%E7%AE%A1%E5%BB%8A%E6%95%B0%E5%AD%97%E5%AD%AA%E7%94%9F%E8%BF%90%E7%BB%B4%E5%AE%9E%E4%BD%93%E6%A0%B7%E5%93%81%E9%A1%B9%E7%9B%AE%E8%AE%A1%E5%88%92%E4%B9%A6_V2.3.docx)
- [docs/综合管廊数字孪生运维实体样品项目计划书_V2.4.docx](https://github.com/x1ng-chen/utility-tunnel-digital-twin/blob/529f8c03e0af2e02f7ab26b827d0af43bc638b0a/docs/%E7%BB%BC%E5%90%88%E7%AE%A1%E5%BB%8A%E6%95%B0%E5%AD%97%E5%AD%AA%E7%94%9F%E8%BF%90%E7%BB%B4%E5%AE%9E%E4%BD%93%E6%A0%B7%E5%93%81%E9%A1%B9%E7%9B%AE%E8%AE%A1%E5%88%92%E4%B9%A6_V2.4.docx)
- [docs/综合管廊数字孪生运维实体样品项目计划书_V2.5.docx](https://github.com/x1ng-chen/utility-tunnel-digital-twin/blob/529f8c03e0af2e02f7ab26b827d0af43bc638b0a/docs/%E7%BB%BC%E5%90%88%E7%AE%A1%E5%BB%8A%E6%95%B0%E5%AD%97%E5%AD%AA%E7%94%9F%E8%BF%90%E7%BB%B4%E5%AE%9E%E4%BD%93%E6%A0%B7%E5%93%81%E9%A1%B9%E7%9B%AE%E8%AE%A1%E5%88%92%E4%B9%A6_V2.5.docx)
- [docs/综合管廊数字孪生运维实体样品项目计划书_V2.6.docx](https://github.com/x1ng-chen/utility-tunnel-digital-twin/blob/529f8c03e0af2e02f7ab26b827d0af43bc638b0a/docs/%E7%BB%BC%E5%90%88%E7%AE%A1%E5%BB%8A%E6%95%B0%E5%AD%97%E5%AD%AA%E7%94%9F%E8%BF%90%E7%BB%B4%E5%AE%9E%E4%BD%93%E6%A0%B7%E5%93%81%E9%A1%B9%E7%9B%AE%E8%AE%A1%E5%88%92%E4%B9%A6_V2.6.docx)
- [docs/综合管廊数字孪生运维实体样品项目计划书_V2.7.docx](https://github.com/x1ng-chen/utility-tunnel-digital-twin/blob/529f8c03e0af2e02f7ab26b827d0af43bc638b0a/docs/%E7%BB%BC%E5%90%88%E7%AE%A1%E5%BB%8A%E6%95%B0%E5%AD%97%E5%AD%AA%E7%94%9F%E8%BF%90%E7%BB%B4%E5%AE%9E%E4%BD%93%E6%A0%B7%E5%93%81%E9%A1%B9%E7%9B%AE%E8%AE%A1%E5%88%92%E4%B9%A6_V2.7.docx)
- [docs/综合管廊数字孪生运维实体样品项目计划书_V2.8.docx](https://github.com/x1ng-chen/utility-tunnel-digital-twin/blob/529f8c03e0af2e02f7ab26b827d0af43bc638b0a/docs/%E7%BB%BC%E5%90%88%E7%AE%A1%E5%BB%8A%E6%95%B0%E5%AD%97%E5%AD%AA%E7%94%9F%E8%BF%90%E7%BB%B4%E5%AE%9E%E4%BD%93%E6%A0%B7%E5%93%81%E9%A1%B9%E7%9B%AE%E8%AE%A1%E5%88%92%E4%B9%A6_V2.8.docx)
- [docs/综合管廊数字孪生运维实体样品项目计划书_V2.9.docx](https://github.com/x1ng-chen/utility-tunnel-digital-twin/blob/529f8c03e0af2e02f7ab26b827d0af43bc638b0a/docs/%E7%BB%BC%E5%90%88%E7%AE%A1%E5%BB%8A%E6%95%B0%E5%AD%97%E5%AD%AA%E7%94%9F%E8%BF%90%E7%BB%B4%E5%AE%9E%E4%BD%93%E6%A0%B7%E5%93%81%E9%A1%B9%E7%9B%AE%E8%AE%A1%E5%88%92%E4%B9%A6_V2.9.docx)
- [docs/综合管廊数字孪生运维实体样品项目计划书_V3.0.docx](https://github.com/x1ng-chen/utility-tunnel-digital-twin/blob/529f8c03e0af2e02f7ab26b827d0af43bc638b0a/docs/%E7%BB%BC%E5%90%88%E7%AE%A1%E5%BB%8A%E6%95%B0%E5%AD%97%E5%AD%AA%E7%94%9F%E8%BF%90%E7%BB%B4%E5%AE%9E%E4%BD%93%E6%A0%B7%E5%93%81%E9%A1%B9%E7%9B%AE%E8%AE%A1%E5%88%92%E4%B9%A6_V3.0.docx)
- [docs/综合管廊数字孪生运维实体样品项目计划书_V3.1_视觉智能扩展版.docx](https://github.com/x1ng-chen/utility-tunnel-digital-twin/blob/529f8c03e0af2e02f7ab26b827d0af43bc638b0a/docs/%E7%BB%BC%E5%90%88%E7%AE%A1%E5%BB%8A%E6%95%B0%E5%AD%97%E5%AD%AA%E7%94%9F%E8%BF%90%E7%BB%B4%E5%AE%9E%E4%BD%93%E6%A0%B7%E5%93%81%E9%A1%B9%E7%9B%AE%E8%AE%A1%E5%88%92%E4%B9%A6_V3.1_%E8%A7%86%E8%A7%89%E6%99%BA%E8%83%BD%E6%89%A9%E5%B1%95%E7%89%88.docx)
- [docs/综合管廊数字孪生运维实体样品项目计划书_V3.2_ESP8266通信基线版.docx](https://github.com/x1ng-chen/utility-tunnel-digital-twin/blob/529f8c03e0af2e02f7ab26b827d0af43bc638b0a/docs/%E7%BB%BC%E5%90%88%E7%AE%A1%E5%BB%8A%E6%95%B0%E5%AD%97%E5%AD%AA%E7%94%9F%E8%BF%90%E7%BB%B4%E5%AE%9E%E4%BD%93%E6%A0%B7%E5%93%81%E9%A1%B9%E7%9B%AE%E8%AE%A1%E5%88%92%E4%B9%A6_V3.2_ESP8266%E9%80%9A%E4%BF%A1%E5%9F%BA%E7%BA%BF%E7%89%88.docx)
- [docs/综合管廊数字孪生运维实体样品项目计划书_V3.3_精简云数据架构版.docx](https://github.com/x1ng-chen/utility-tunnel-digital-twin/blob/529f8c03e0af2e02f7ab26b827d0af43bc638b0a/docs/%E7%BB%BC%E5%90%88%E7%AE%A1%E5%BB%8A%E6%95%B0%E5%AD%97%E5%AD%AA%E7%94%9F%E8%BF%90%E7%BB%B4%E5%AE%9E%E4%BD%93%E6%A0%B7%E5%93%81%E9%A1%B9%E7%9B%AE%E8%AE%A1%E5%88%92%E4%B9%A6_V3.3_%E7%B2%BE%E7%AE%80%E4%BA%91%E6%95%B0%E6%8D%AE%E6%9E%B6%E6%9E%84%E7%89%88.docx)
- [docs/综合管廊数字孪生运维实体样品项目计划书_V3.4_当前进度与执行计划版.docx](https://github.com/x1ng-chen/utility-tunnel-digital-twin/blob/529f8c03e0af2e02f7ab26b827d0af43bc638b0a/docs/%E7%BB%BC%E5%90%88%E7%AE%A1%E5%BB%8A%E6%95%B0%E5%AD%97%E5%AD%AA%E7%94%9F%E8%BF%90%E7%BB%B4%E5%AE%9E%E4%BD%93%E6%A0%B7%E5%93%81%E9%A1%B9%E7%9B%AE%E8%AE%A1%E5%88%92%E4%B9%A6_V3.4_%E5%BD%93%E5%89%8D%E8%BF%9B%E5%BA%A6%E4%B8%8E%E6%89%A7%E8%A1%8C%E8%AE%A1%E5%88%92%E7%89%88.docx)
- [docs/综合管廊数字孪生运维实体样品项目计划书_V3.5_硬件数量与型号冻结版.docx](https://github.com/x1ng-chen/utility-tunnel-digital-twin/blob/529f8c03e0af2e02f7ab26b827d0af43bc638b0a/docs/%E7%BB%BC%E5%90%88%E7%AE%A1%E5%BB%8A%E6%95%B0%E5%AD%97%E5%AD%AA%E7%94%9F%E8%BF%90%E7%BB%B4%E5%AE%9E%E4%BD%93%E6%A0%B7%E5%93%81%E9%A1%B9%E7%9B%AE%E8%AE%A1%E5%88%92%E4%B9%A6_V3.5_%E7%A1%AC%E4%BB%B6%E6%95%B0%E9%87%8F%E4%B8%8E%E5%9E%8B%E5%8F%B7%E5%86%BB%E7%BB%93%E7%89%88.docx)
- [docs/综合管廊数字孪生运维实体样品项目计划书_V3.6_液位监测与水路建模版.docx](https://github.com/x1ng-chen/utility-tunnel-digital-twin/blob/529f8c03e0af2e02f7ab26b827d0af43bc638b0a/docs/%E7%BB%BC%E5%90%88%E7%AE%A1%E5%BB%8A%E6%95%B0%E5%AD%97%E5%AD%AA%E7%94%9F%E8%BF%90%E7%BB%B4%E5%AE%9E%E4%BD%93%E6%A0%B7%E5%93%81%E9%A1%B9%E7%9B%AE%E8%AE%A1%E5%88%92%E4%B9%A6_V3.6_%E6%B6%B2%E4%BD%8D%E7%9B%91%E6%B5%8B%E4%B8%8E%E6%B0%B4%E8%B7%AF%E5%BB%BA%E6%A8%A1%E7%89%88.docx)
- [docs/综合管廊数字孪生运维实体样品项目计划书_V3.7_气体传感器到货与接入计划版.docx](https://github.com/x1ng-chen/utility-tunnel-digital-twin/blob/529f8c03e0af2e02f7ab26b827d0af43bc638b0a/docs/%E7%BB%BC%E5%90%88%E7%AE%A1%E5%BB%8A%E6%95%B0%E5%AD%97%E5%AD%AA%E7%94%9F%E8%BF%90%E7%BB%B4%E5%AE%9E%E4%BD%93%E6%A0%B7%E5%93%81%E9%A1%B9%E7%9B%AE%E8%AE%A1%E5%88%92%E4%B9%A6_V3.7_%E6%B0%94%E4%BD%93%E4%BC%A0%E6%84%9F%E5%99%A8%E5%88%B0%E8%B4%A7%E4%B8%8E%E6%8E%A5%E5%85%A5%E8%AE%A1%E5%88%92%E7%89%88.docx)

### 已退出运行与门禁的 V01–V05 模型资料（37 个）

- [model/asset-map-v05-final.json](https://github.com/x1ng-chen/utility-tunnel-digital-twin/blob/529f8c03e0af2e02f7ab26b827d0af43bc638b0a/model/asset-map-v05-final.json)
- [model/asset-map.json](https://github.com/x1ng-chen/utility-tunnel-digital-twin/blob/529f8c03e0af2e02f7ab26b827d0af43bc638b0a/model/asset-map.json)
- [model/fabrication/utility-tunnel-ring-build-pack-v01.md](https://github.com/x1ng-chen/utility-tunnel-digital-twin/blob/529f8c03e0af2e02f7ab26b827d0af43bc638b0a/model/fabrication/utility-tunnel-ring-build-pack-v01.md)
- [model/iteration_review.json](https://github.com/x1ng-chen/utility-tunnel-digital-twin/blob/529f8c03e0af2e02f7ab26b827d0af43bc638b0a/model/iteration_review.json)
- [model/previews/utility-tunnel-annular-v04-functional.png](https://github.com/x1ng-chen/utility-tunnel-digital-twin/blob/529f8c03e0af2e02f7ab26b827d0af43bc638b0a/model/previews/utility-tunnel-annular-v04-functional.png)
- [model/previews/utility-tunnel-annular-v04-hero.png](https://github.com/x1ng-chen/utility-tunnel-digital-twin/blob/529f8c03e0af2e02f7ab26b827d0af43bc638b0a/model/previews/utility-tunnel-annular-v04-hero.png)
- [model/previews/utility-tunnel-annular-v05-final-hero.png](https://github.com/x1ng-chen/utility-tunnel-digital-twin/blob/529f8c03e0af2e02f7ab26b827d0af43bc638b0a/model/previews/utility-tunnel-annular-v05-final-hero.png)
- [model/previews/utility-tunnel-annular-v05-final-levels.png](https://github.com/x1ng-chen/utility-tunnel-digital-twin/blob/529f8c03e0af2e02f7ab26b827d0af43bc638b0a/model/previews/utility-tunnel-annular-v05-final-levels.png)
- [model/previews/utility-tunnel-rectangular-v03-functional.png](https://github.com/x1ng-chen/utility-tunnel-digital-twin/blob/529f8c03e0af2e02f7ab26b827d0af43bc638b0a/model/previews/utility-tunnel-rectangular-v03-functional.png)
- [model/previews/utility-tunnel-rectangular-v03-hero.png](https://github.com/x1ng-chen/utility-tunnel-digital-twin/blob/529f8c03e0af2e02f7ab26b827d0af43bc638b0a/model/previews/utility-tunnel-rectangular-v03-hero.png)
- [model/previews/utility-tunnel-ring-v01-before-detail.png](https://github.com/x1ng-chen/utility-tunnel-digital-twin/blob/529f8c03e0af2e02f7ab26b827d0af43bc638b0a/model/previews/utility-tunnel-ring-v01-before-detail.png)
- [model/previews/utility-tunnel-ring-v01-hero.png](https://github.com/x1ng-chen/utility-tunnel-digital-twin/blob/529f8c03e0af2e02f7ab26b827d0af43bc638b0a/model/previews/utility-tunnel-ring-v01-hero.png)
- [model/previews/utility-tunnel-ring-v02-functional.png](https://github.com/x1ng-chen/utility-tunnel-digital-twin/blob/529f8c03e0af2e02f7ab26b827d0af43bc638b0a/model/previews/utility-tunnel-ring-v02-functional.png)
- [model/previews/utility-tunnel-ring-v02-hero.png](https://github.com/x1ng-chen/utility-tunnel-digital-twin/blob/529f8c03e0af2e02f7ab26b827d0af43bc638b0a/model/previews/utility-tunnel-ring-v02-hero.png)
- [model/utility-tunnel-annular-v04-contract.json](https://github.com/x1ng-chen/utility-tunnel-digital-twin/blob/529f8c03e0af2e02f7ab26b827d0af43bc638b0a/model/utility-tunnel-annular-v04-contract.json)
- [model/utility-tunnel-annular-v04.blend](https://github.com/x1ng-chen/utility-tunnel-digital-twin/blob/529f8c03e0af2e02f7ab26b827d0af43bc638b0a/model/utility-tunnel-annular-v04.blend)
- [model/utility-tunnel-annular-v04.glb](https://github.com/x1ng-chen/utility-tunnel-digital-twin/blob/529f8c03e0af2e02f7ab26b827d0af43bc638b0a/model/utility-tunnel-annular-v04.glb)
- [model/utility-tunnel-annular-v05-final.blend](https://github.com/x1ng-chen/utility-tunnel-digital-twin/blob/529f8c03e0af2e02f7ab26b827d0af43bc638b0a/model/utility-tunnel-annular-v05-final.blend)
- [model/utility-tunnel-annular-v05-final.glb](https://github.com/x1ng-chen/utility-tunnel-digital-twin/blob/529f8c03e0af2e02f7ab26b827d0af43bc638b0a/model/utility-tunnel-annular-v05-final.glb)
- [model/utility-tunnel-rectangular-v03-contract.json](https://github.com/x1ng-chen/utility-tunnel-digital-twin/blob/529f8c03e0af2e02f7ab26b827d0af43bc638b0a/model/utility-tunnel-rectangular-v03-contract.json)
- [model/utility-tunnel-rectangular-v03.blend](https://github.com/x1ng-chen/utility-tunnel-digital-twin/blob/529f8c03e0af2e02f7ab26b827d0af43bc638b0a/model/utility-tunnel-rectangular-v03.blend)
- [model/utility-tunnel-rectangular-v03.glb](https://github.com/x1ng-chen/utility-tunnel-digital-twin/blob/529f8c03e0af2e02f7ab26b827d0af43bc638b0a/model/utility-tunnel-rectangular-v03.glb)
- [model/utility-tunnel-ring-three-view-v02.png](https://github.com/x1ng-chen/utility-tunnel-digital-twin/blob/529f8c03e0af2e02f7ab26b827d0af43bc638b0a/model/utility-tunnel-ring-three-view-v02.png)
- [model/utility-tunnel-ring-three-view-v02.svg](https://github.com/x1ng-chen/utility-tunnel-digital-twin/blob/529f8c03e0af2e02f7ab26b827d0af43bc638b0a/model/utility-tunnel-ring-three-view-v02.svg)
- [model/utility-tunnel-ring-three-view.png](https://github.com/x1ng-chen/utility-tunnel-digital-twin/blob/529f8c03e0af2e02f7ab26b827d0af43bc638b0a/model/utility-tunnel-ring-three-view.png)
- [model/utility-tunnel-ring-three-view.svg](https://github.com/x1ng-chen/utility-tunnel-digital-twin/blob/529f8c03e0af2e02f7ab26b827d0af43bc638b0a/model/utility-tunnel-ring-three-view.svg)
- [model/utility-tunnel-ring-v01-functional-notes.md](https://github.com/x1ng-chen/utility-tunnel-digital-twin/blob/529f8c03e0af2e02f7ab26b827d0af43bc638b0a/model/utility-tunnel-ring-v01-functional-notes.md)
- [model/utility-tunnel-ring-v01.blend](https://github.com/x1ng-chen/utility-tunnel-digital-twin/blob/529f8c03e0af2e02f7ab26b827d0af43bc638b0a/model/utility-tunnel-ring-v01.blend)
- [model/utility-tunnel-ring-v01.glb](https://github.com/x1ng-chen/utility-tunnel-digital-twin/blob/529f8c03e0af2e02f7ab26b827d0af43bc638b0a/model/utility-tunnel-ring-v01.glb)
- [model/utility-tunnel-ring-v02-contract.json](https://github.com/x1ng-chen/utility-tunnel-digital-twin/blob/529f8c03e0af2e02f7ab26b827d0af43bc638b0a/model/utility-tunnel-ring-v02-contract.json)
- [model/utility-tunnel-ring-v02-validation.md](https://github.com/x1ng-chen/utility-tunnel-digital-twin/blob/529f8c03e0af2e02f7ab26b827d0af43bc638b0a/model/utility-tunnel-ring-v02-validation.md)
- [model/utility-tunnel-ring-v02.blend](https://github.com/x1ng-chen/utility-tunnel-digital-twin/blob/529f8c03e0af2e02f7ab26b827d0af43bc638b0a/model/utility-tunnel-ring-v02.blend)
- [model/utility-tunnel-ring-v02.glb](https://github.com/x1ng-chen/utility-tunnel-digital-twin/blob/529f8c03e0af2e02f7ab26b827d0af43bc638b0a/model/utility-tunnel-ring-v02.glb)
- [model/utility_tunnel_annular_v04.py](https://github.com/x1ng-chen/utility-tunnel-digital-twin/blob/529f8c03e0af2e02f7ab26b827d0af43bc638b0a/model/utility_tunnel_annular_v04.py)
- [model/utility_tunnel_annular_v05_final.py](https://github.com/x1ng-chen/utility-tunnel-digital-twin/blob/529f8c03e0af2e02f7ab26b827d0af43bc638b0a/model/utility_tunnel_annular_v05_final.py)
- [model/utility_tunnel_rectangular_v03.py](https://github.com/x1ng-chen/utility-tunnel-digital-twin/blob/529f8c03e0af2e02f7ab26b827d0af43bc638b0a/model/utility_tunnel_rectangular_v03.py)
- [model/utility_tunnel_ring_v01.py](https://github.com/x1ng-chen/utility-tunnel-digital-twin/blob/529f8c03e0af2e02f7ab26b827d0af43bc638b0a/model/utility_tunnel_ring_v01.py)

### 已停用的蓝牙串口网关（4 个）

- [services/serial-gateway/.env.example](https://github.com/x1ng-chen/utility-tunnel-digital-twin/blob/529f8c03e0af2e02f7ab26b827d0af43bc638b0a/services/serial-gateway/.env.example)
- [services/serial-gateway/package-lock.json](https://github.com/x1ng-chen/utility-tunnel-digital-twin/blob/529f8c03e0af2e02f7ab26b827d0af43bc638b0a/services/serial-gateway/package-lock.json)
- [services/serial-gateway/package.json](https://github.com/x1ng-chen/utility-tunnel-digital-twin/blob/529f8c03e0af2e02f7ab26b827d0af43bc638b0a/services/serial-gateway/package.json)
- [services/serial-gateway/src/index.js](https://github.com/x1ng-chen/utility-tunnel-digital-twin/blob/529f8c03e0af2e02f7ab26b827d0af43bc638b0a/services/serial-gateway/src/index.js)

### 旧计划书与概念三视图生成脚本（9 个）

- [tools/build_plan.py](https://github.com/x1ng-chen/utility-tunnel-digital-twin/blob/529f8c03e0af2e02f7ab26b827d0af43bc638b0a/tools/build_plan.py)
- [tools/build_plan_v2.py](https://github.com/x1ng-chen/utility-tunnel-digital-twin/blob/529f8c03e0af2e02f7ab26b827d0af43bc638b0a/tools/build_plan_v2.py)
- [tools/freeze_1m_dimensions.py](https://github.com/x1ng-chen/utility-tunnel-digital-twin/blob/529f8c03e0af2e02f7ab26b827d0af43bc638b0a/tools/freeze_1m_dimensions.py)
- [tools/generate_ring_three_view.py](https://github.com/x1ng-chen/utility-tunnel-digital-twin/blob/529f8c03e0af2e02f7ab26b827d0af43bc638b0a/tools/generate_ring_three_view.py)
- [tools/generate_ring_three_view_v02.py](https://github.com/x1ng-chen/utility-tunnel-digital-twin/blob/529f8c03e0af2e02f7ab26b827d0af43bc638b0a/tools/generate_ring_three_view_v02.py)
- [tools/update_plan_v26.py](https://github.com/x1ng-chen/utility-tunnel-digital-twin/blob/529f8c03e0af2e02f7ab26b827d0af43bc638b0a/tools/update_plan_v26.py)
- [tools/update_plan_v27.py](https://github.com/x1ng-chen/utility-tunnel-digital-twin/blob/529f8c03e0af2e02f7ab26b827d0af43bc638b0a/tools/update_plan_v27.py)
- [tools/update_project_plan_v35.py](https://github.com/x1ng-chen/utility-tunnel-digital-twin/blob/529f8c03e0af2e02f7ab26b827d0af43bc638b0a/tools/update_project_plan_v35.py)
- [tools/update_project_plan_v36.py](https://github.com/x1ng-chen/utility-tunnel-digital-twin/blob/529f8c03e0af2e02f7ab26b827d0af43bc638b0a/tools/update_project_plan_v36.py)
