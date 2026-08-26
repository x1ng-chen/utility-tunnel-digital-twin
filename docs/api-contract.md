# 软件平台 API 契约（P1）

> 版本：v1.0 · 更新：2026-08-26

前端通过 `apps/web/app/lib/operations-api.ts` 调用 `services/api`。浏览器使用短时 JWT；令牌仅保留在页面内存，绝不写入 `localStorage`、导出文件或仓库。

## 接入规则

1. 前端可用 `NEXT_PUBLIC_API_BASE_URL` 提供默认 API 地址，也可在页面顶部切换到“API”后手动输入。
2. API 必须在 `WEB_ORIGIN` 中允许前端的实际 Origin；开发环境默认 `http://localhost:5173`。
3. 任何写操作由服务端再次校验 JWT、RBAC、输入和状态机；前端按钮不能视为授权依据。
4. 前端写入后立即乐观更新，再从 API 完整回读；失败时恢复服务端状态并展示错误。

## 接口清单

| 接口 | 权限 | 前端用途 |
| --- | --- | --- |
| `POST /v1/auth/login` | 公开 | 获取 15 分钟访问令牌和用户角色 |
| `GET /v1/dashboard/overview` | `dashboard.read` | 运行摘要与最新遥测 |
| `GET /v1/assets?q=&zone=&status=` | `asset.read` | 台账、检索、孪生资产映射 |
| `GET /v1/alerts` | `alert.read` | 告警清单 |
| `POST /v1/alerts/:id/acknowledge` | `alert.acknowledge` | 确认告警 |
| `POST /v1/alerts/:id/work-orders` | `work_order.write` | 从告警创建唯一来源工单 |
| `GET /v1/work-orders` | `work_order.read` | 工单看板 |
| `POST /v1/work-orders` | `work_order.write` | 新建手工工单 |
| `POST /v1/work-orders/:id/transition` | `work_order.write`，完成时还需 `work_order.review` | 受控流转与告警闭环 |
| `GET /v1/thresholds` | `setting.read` | 读取阈值 |
| `PUT /v1/thresholds/:key` | `setting.write` | 更新阈值及版本号 |
| `POST /v1/report-exports` | `dashboard.read` | 登记浏览器生成的 CSV/JSON 导出 |
| `GET /v1/audit` | `audit.read` | 审计追踪 |

## 核心写入约束

- 同一来源告警只能创建一张关联工单（数据库唯一索引）。
- 工单必须按 `待派发 → 处理中 → 待复核 → 已完成` 流转；完成来源工单时，服务端在同一事务中恢复其告警并在无活动告警时恢复资产状态。
- 阈值请求必须携带当前 `version` 并满足 `0 ≤ warning < alarm`；数据库仅在版本一致时递增。未知阈值返回 `404`，并发修改返回 `409 version_conflict`，前端必须重新读取后再提交。
- 报表文件由浏览器下载；API 只登记可审计的导出元数据，不接收用户下载内容。
