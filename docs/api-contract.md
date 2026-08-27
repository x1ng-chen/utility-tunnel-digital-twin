# 软件平台 API 契约（P1）

> 版本：v1.1 · 更新：2026-08-27

本文件同时保留旧版 Node API 与当前 Vue 3 / Django API 的边界，便于迁移期间按入口区分调用方。旧版业务代码不在本阶段修改。

## 旧版 Node API（维护兼容）

前端通过 `apps/web/app/lib/operations-api.ts` 调用 `services/api`。浏览器使用短时 JWT；令牌仅保留在页面内存，绝不写入 `localStorage`、导出文件或仓库。

### 接入规则

1. 前端可用 `NEXT_PUBLIC_API_BASE_URL` 提供默认 API 地址，也可在页面顶部切换到“API”后手动输入。
2. API 必须在 `WEB_ORIGIN` 中允许前端的实际 Origin；开发环境默认 `http://localhost:5173`。
3. 任何写操作由服务端再次校验 JWT、RBAC、输入和状态机；前端按钮不能视为授权依据。
4. 前端写入后立即乐观更新，再从 API 完整回读；失败时恢复服务端状态并展示错误。

### 接口清单

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

### 核心写入约束

- 同一来源告警只能创建一张关联工单（数据库唯一索引）。
- 工单必须按 `待派发 → 处理中 → 待复核 → 已完成` 流转；完成来源工单时，服务端在同一事务中恢复其告警并在无活动告警时恢复资产状态。
- 阈值请求必须携带当前 `version` 并满足 `0 ≤ warning < alarm`；数据库仅在版本一致时递增。未知阈值返回 `404`，并发修改返回 `409 version_conflict`，前端必须重新读取后再提交。
- 报表文件由浏览器下载；API 只登记可审计的导出元数据，不接收用户下载内容。

---

# Vue 3 / Django API 契约

本文档是前端与后端的最小可执行契约。所有业务接口使用 `Bearer` Token，响应 JSON 使用 camelCase 字段。

## 通用约定

- 地址前缀：`/api/`
- 请求追踪：客户端发送 `X-Request-Id`，服务端在响应头原样返回或生成新的 ID。
- 列表响应：

  ```json
  {
    "items": [],
    "page": 1,
    "pageSize": 20,
    "total": 0,
    "pageCount": 0,
    "hasNext": false,
    "hasPrevious": false
  }
  ```

- 列表默认按主键倒序返回（最新记录优先）；调用方应使用返回的 `page`、`pageCount` 和 `hasNext` 控制翻页，不要依赖本地数组顺序。

- 失败响应：

  ```json
  {
    "error": "invalid_request",
    "message": "可读的错误说明",
    "details": {}
  }
  ```

  `error` 用于程序判断，`message` 用于界面展示，`details` 用于字段级错误。写操作的状态冲突使用 `409`，权限不足使用 `403`，未登录或 Token 过期使用 `401`。

## 身份与健康检查

| 方法 | 路径 | 权限 | 说明 |
| --- | --- | --- | --- |
| `POST` | `/auth/login/` | 公开 | `{ email, password }`，返回 `accessToken`、`tokenType` 和 `user` |
| `GET` | `/auth/me/` | 登录 | 返回当前用户及角色 |
| `POST` | `/auth/logout/` | 登录 | 撤销当前用户 Token |
| `GET` | `/health/` | 公开 | 进程存活检查 |
| `GET` | `/ready/` | 公开 | 数据库可用性检查 |

## 运维业务接口

| 方法 | 路径 | 权限 | 说明 |
| --- | --- | --- | --- |
| `GET` | `/dashboard/` | 登录 | 资产、健康度、告警、工单和最新遥测汇总 |
| `GET` | `/assets/` | 登录 | `search`、`status`、`zone`、`page`、`pageSize` |
| `GET` | `/alerts/` | 登录 | `status`、`severity`、`page`、`pageSize` |
| `POST` | `/alerts/{id}/acknowledge/` | 管理员/运维员 | 确认待处理告警 |
| `POST` | `/alerts/{id}/work-order/` | 管理员/运维员 | 从告警创建关联工单 |
| `GET` | `/work-orders/` | 登录 | `status`、`search`、`page`、`pageSize` |
| `POST` | `/work-orders/` | 管理员/运维员 | 新建 `{ assetCode, title, description?, priority? }` |
| `POST` | `/work-orders/{id}/transition/` | 管理员/运维员 | 流转 `{ to }`；完成工单必须管理员复核 |
| `GET` | `/telemetry/` | 登录 | `assetCode`、`page`、`pageSize` |
| `GET` | `/thresholds/` | 登录 | 查询阈值策略 |
| `PUT` | `/thresholds/{key}/` | 管理员 | 更新 `{ warning, alarm, version }`，使用乐观锁 |
| `GET` | `/audit/` | 登录 | `action`、`search`（动作、资源类型/编号或操作者邮箱）、`page`、`pageSize` |
| `GET` | `/report-exports/` | 登录 | 导出操作记录 |
| `POST` | `/report-exports/` | 登录 | 创建 `{ report: alerts\|workOrders\|assets\|daily }` |

## 角色边界

| 操作 | 管理员 | 运维员 | 查看者 |
| --- | --- | --- | --- |
| 查询业务数据 | ✓ | ✓ | ✓ |
| 确认告警 | ✓ | ✓ | — |
| 新建/流转工单 | ✓ | ✓ | — |
| 完成工单复核 | ✓ | — | — |
| 修改阈值 | ✓ | — | — |
| 导出报表 | ✓ | ✓ | ✓ |

任何未列出的写操作默认拒绝，后端权限校验是最终边界，前端按钮隐藏仅用于改善使用体验。
