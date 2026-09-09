# 软件验收清单

> 版本：P0–P3 · 更新：2026-09-08；此表列验收要求，并非完成勾选表。

| 类别 | 验收项 | 可验证证据 |
| --- | --- | --- |
| P0 范围 | README、架构、接口与演示边界没有 SQLite/待实施的冲突表述 | `README.md`、`docs/api-contract.md`、`docs/software-platform.md` |
| P1 接入 | 前端连接 Django API，核验构建地址与浏览器地址覆盖；人员令牌只写当前会话，IoTDA 使用仅限遥测 POST 的机器密钥 | `frontend/src/services/api.ts`、`frontend/src/stores/auth.ts`、`operations/authentication.py` |
| P1 业务 | 告警确认、来源工单、手工工单、受控流转、阈值、导出均经服务端 RBAC、事务与审计；提交复核和完成复核强制填写说明并形成工单处理时间线 | API 冒烟脚本、`WorkOrderEvent` 与 `audit_log` |
| P1 数据库 | 迁移、种子、最小权限运行账号、备份恢复步骤可复现 | `migrations/`、`deploy/postgres/provision.sql`、部署手册 |
| P0 上线预检 | 正式流量前验证生产安全配置、TLS 反向代理信任、数据库 TLS、共享缓存、数据库连通性和迁移状态 | `python manage.py production_preflight`、`deploy/postgres/provision.sql` |
| P2 孪生 | GLB 节点按设备编码绑定；支持状态着色、告警定位、异常巡检、快速切换、全屏指针和模型缺失节点校验 | `TwinScene.vue`、`Twin3DView.vue`、`twin3d.ts`、`docs/3D模型接入规范.md` |
| P2 GIS 治理 | 管理员可原子导入、审核、发布 WGS84 GeoJSON；已发布空间对象才进入运维地图，所有变更可审计 | `SpatialFeature`、`/api/gis/features/`、空间数据管理页面 |
| P2 接口预留 | 每个盘点资产的通信协议、端点、设备标识与期望心跳可版本化管理；预留不等于在线 | `HardwareBinding`、`/api/hardware-bindings/` |
| P2 质量 | 静态检查、前后端与网关单元测试、生产构建、迁移一致性和依赖审计自动执行 | `.github/workflows/vue-django.yml`、`.github/workflows/ci.yml` |
| P2 浏览器回归 | 登录、孪生筛选、告警确认、Django API 数据读取和审计的真实浏览器 E2E | `.github/workflows/browser-e2e.yml`；首次绿色运行后归档工作流链接 |
| P2 韧性 | 健康/就绪检查、结构化日志、速率限制、安全响应头、统一错误码与前端失败提示 | `backend/operations/views.py`、`backend/operations/middleware.py`、`backend/operations/throttling.py`、`AppShell.vue` |
| P2 数据治理 | 遥测、审计、导出数据按保留期只读盘点，清理操作必须单独审批 | `python manage.py data_governance_report --format=json` |
| P2 数据洞察 | 遥测历史按业务时间稳定排序，可按资产、指标、质量和时间查询并获得一致的聚合与最新样本 | `/api/telemetry/`、`/api/telemetry/summary/`、数据洞察页面和前后端测试 |
| P2 发布制品 | Vue 静态站与 Django API 具备可审查容器制品、非 root 运行、内部 API 网络与运行时密钥注入 | `deploy/containers/`、`tools/check-deployment-artifacts.mjs` |
| P3 交付 | 部署、使用、测试与答辩脚本完整，可独立演示；实体参数、生产云资源与候选模型等外部输入明确列为验收前置条件 | `docs/` 下交付文档 |

## 不纳入本轮验收

- 硬件现场安装、执行器控制和工业安全认证；
- 未提供账号或未授权创建的生产托管 PostgreSQL 实例；
- Blender 源模型的后续团队建模修改。当前仓库已包含可加载的 GLB 运行时模型、设备节点映射与缺失节点校验。
