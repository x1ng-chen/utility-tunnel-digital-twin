# 软件验收清单

> 版本：P0–P3 · 更新：2026-08-26

| 类别 | 验收项 | 可验证证据 |
| --- | --- | --- |
| P0 范围 | README、架构、接口与演示边界没有 SQLite/待实施的冲突表述 | `README.md`、`docs/api-contract.md`、`docs/software-platform.md` |
| P1 接入 | 前端可在本地与 API 模式间切换，令牌不写入浏览器持久化存储 | `operations-api.ts`、`use-operations.ts`、页面连接卡片 |
| P1 业务 | 告警确认、来源工单、手工工单、受控流转、阈值、导出均经服务端 RBAC、事务与审计 | API 冒烟脚本与 `audit_log` |
| P1 数据库 | 迁移、种子、最小权限运行账号、备份恢复步骤可复现 | `migrations/`、`deploy/postgres/provision.sql`、部署手册 |
| P0 上线预检 | 正式流量前验证生产安全配置、TLS 反向代理信任、数据库 TLS、共享缓存、数据库连通性和迁移状态 | `python manage.py production_preflight`、`deploy/postgres/provision.sql` |
| P2 孪生 | 区域与资产坐标独立配置；数据库空间坐标可覆盖视觉回退位置 | `twin-config.ts` 与孪生视图 |
| P2 质量 | 静态检查、类型检查、单元测试、覆盖率、构建、迁移安全检查与 PostgreSQL 冒烟都自动执行 | `.github/workflows/vue-django.yml`、`.github/workflows/ci.yml` |
| P2 浏览器回归 | 登录、孪生筛选、告警确认、Django API 数据读取和审计的真实浏览器 E2E | `.github/workflows/browser-e2e.yml`；首次绿色运行后归档工作流链接 |
| P2 韧性 | 健康/就绪检查、结构化日志、速率限制、安全响应头、统一错误码与前端失败提示 | `server.ts`、`rate-limit.ts` |
| P2 数据治理 | 遥测、审计、导出数据按保留期只读盘点，清理操作必须单独审批 | `python manage.py data_governance_report --format=json` |
| P2 发布制品 | Vue 静态站与 Django API 具备可审查容器制品、非 root 运行、内部 API 网络与运行时密钥注入 | `deploy/containers/`、`tools/check-deployment-artifacts.mjs` |
| P3 交付 | 部署、使用、测试与答辩脚本完整，可独立演示 | `docs/` 下交付文档 |

## 不纳入本轮验收

- 硬件、MQTT、现场控制、真实传感器与工业安全认证；
- 未提供账号或未授权创建的托管 PostgreSQL 实例；
- 真实三维 GLB 模型资产。当前提供的是可配置空间示意和数据库坐标联动，后续可将同一资产坐标/网格映射接入 GLB。
