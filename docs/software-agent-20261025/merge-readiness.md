# PR #38 合并前检查修复

2026-10-25。首轮GitHub Actions在功能测试/构建之外发现了发布检查失败。本次保留原有检查、审计阈值、WebSocket和ASGI服务，修复依赖与执行环境后重跑。

## 首轮失败与对应修复

| 检查 | 原因 | 修复 |
| --- | --- | --- |
| Repository safety scan | 前端锁文件存在npmmirror下载地址 | 逐个向官方npm元数据核对完整性并改为官方tarball地址；随后按原有semver范围刷新锁文件 |
| Vue3 quality | Vue服务端渲染器、follow-redirects、source-map-js存在高危通告 | Vue锁定3.5.44、follow-redirects 1.16.1、source-map-js 1.2.2；Vue最低约束提高至3.5.42，未强制升级工具主版本 |
| Django quality | DRF 3.18.0及Twisted 26.4.0被依赖审计拒绝 | 升级DRF 3.18.3；临时明确锁定Twisted 26.10.0rc1，保留TLS extras，使用官方PyPI发布文件哈希 |
| Browser end-to-end regression | ubuntu-latest已转向26.04，固定Playwright 1.55.0无法安装其浏览器依赖 | 将浏览器任务固定在Ubuntu 24.04；测试和浏览器安装步骤保留 |

## Twisted候选版的边界

当前官方稳定版仍为26.4.0；26.10.0rc1为[上游安全修复候选版](https://github.com/twisted/twisted/releases/tag/twisted-26.10.0rc1)。已检查官方wheel中的IMAP通配符处理，包含[转义非通配符输入的修复](https://github.com/twisted/twisted/commit/2f8a3c29246f4eb324690e06a9767a11dc4aec9f)，并由原命令`pip-audit --disable-pip --require-hashes -r requirements.lock`验证，未加入任何CVE忽略项。

这是显式的临时依赖选择，不代表候选版已成为正式稳定版；正式26.10.x可用后，应重新执行哈希安装、漏洞审计、HTTP/WebSocket回归，再更换锁文件。没有在本轮部署到公网。

## 验证范围

- 后端依赖按哈希安装，审计报告无已知漏洞。
- 前端沿用原生产审计命令`npm audit --omit=dev --audit-level=high`；阈值未降低。剩余中等风险构建依赖以及开发工具审计预警不在此处宣称清零，工具主版本升级需独立回归。
- 本地重新运行后端全量测试、前端全量测试与生产构建；仓库安全、PostgreSQL策略、部署制品和模型制品检查保持启用。
- 真实浏览器任务结果以本轮GitHub Actions为准；仅修复安装环境不等于浏览器回归已通过。

## 与模型协作者交付整合

合并前同步main的PR #37（f02c22f），保留V16/V17交付包原始字节、哈希清单及LFS规则。重复的V17文件仅有换行差异；软件分支新增的接入段落迁移至本说明，避免修改已发布模型包。

前端已通过`frontend/src/utils/fanMotion.ts`和`TwinScene.vue`接入独立叶轮遥测；实物联调、台账身份核验和管理员模型启用仍未完成。模型重建所需的V16基线随PR #37一并保留；使用可编辑BLEND前应复制另存。
