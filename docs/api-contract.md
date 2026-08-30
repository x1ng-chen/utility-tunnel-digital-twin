# 软件平台 API 契约（Vue 3 / Django）

> 版本：v1.4 · 更新：2026-08-30

本文档是当前正式 Vue 3 前端与 Django API 的最小可执行契约。所有业务接口使用 `Bearer` Token，响应 JSON 使用 camelCase 字段。

## 通用约定

- 地址前缀：`/api/`
- 请求追踪：客户端发送 `X-Request-Id`，服务端在响应头原样返回或生成新的 ID。
- 请求追踪：服务端对合法的 `X-Request-Id` 做长度和字符集校验；异常响应（包括 404/500）也会返回 `X-Request-Id` 响应头，便于按日志关联故障。
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

- 写入事务：会产生业务记录和审计记录的操作必须在同一个数据库事务中完成；审计写入失败时业务写入一并回滚。
- 幂等写入：手工建单和报表登记可通过 `Idempotency-Key`（1-80 个字母、数字、`.`、`_`、`:`、`-`）安全重试；相同用户和相同请求返回原记录，不同负载或不同用户复用该键返回 `409 conflict`。

## 身份与健康检查

| 方法 | 路径 | 权限 | 说明 |
| --- | --- | --- | --- |
| `POST` | `/auth/login/` | 公开 | `{ email, password }`，返回 `accessToken`、`tokenType` 和 `user` |
| `POST` | `/auth/registration-requests/` | 公开 | 提交无密码账号申请 `{ account, displayName, role }` |
| `POST` | `/auth/registration-requests/setup/` | 公开 | 在请求体提交 `{ token, password }` 完成一次性密码设置；凭据不进入路径、查询参数或访问日志 |
| `GET` | `/auth/me/` | 登录 | 返回当前用户及角色 |
| `POST` | `/auth/password/` | 登录 | `{ currentPassword, newPassword }`；验证旧密码和密码强度后更新密码，撤销旧 Token 并返回当前会话的替换 Token |
| `POST` | `/auth/logout/` | 登录 | 撤销当前用户 Token |
| `GET` | `/admin/users/` | 管理员 | 用户检索和状态筛选 |
| `POST` | `/admin/users/` | 管理员 | 创建用户和角色 |
| `PATCH` | `/admin/users/{id}/` | 管理员 | 修改显示名、角色、启停用状态或密码 |
| `GET` | `/admin/registration-requests/` | 管理员 | 按 `pending\|approved\|rejected` 查询账号申请 |
| `PATCH` | `/admin/registration-requests/{id}/` | 管理员 | 批准或驳回申请；驳回必须填写 `reviewNote` |
| `POST` | `/admin/registration-requests/{id}/setup-token/` | 管理员 | 为已批准但尚未设置密码的停用账号轮换一次性凭据，使旧链接立即失效 |
| `GET` | `/health/` | 公开 | 进程存活检查，返回版本和提交标识 |
| `GET` | `/ready/` | 公开 | 数据库可用性检查，返回数据库状态和查询耗时 |

## 运维业务接口

| 方法 | 路径 | 权限 | 说明 |
| --- | --- | --- | --- |
| `GET` | `/dashboard/` | 登录 | 资产、健康度、告警、工单和最新遥测汇总；在线数按硬件绑定期望上报间隔和最近心跳判定，`workOrderSla` 提供已超时和 4 小时内到期工单数 |
| `GET` | `/assets/` | 登录 | `search`、`status`、`zone`、`integrationStatus`、`hardwareCode`、`hasLocation=true\|false`、`isActive=true\|false`、`page`、`pageSize`；管理员可用 `isActive=all` 查询全部生命周期；返回硬件接入信息、WGS84 坐标、坐标来源和版本 |
| `POST` | `/assets/` | 管理员 | 新建资产主数据；校验编码、硬件编号、能力去重、二维孪生坐标和成对 WGS84 坐标，成功后写入审计 |
| `PATCH` | `/assets/{id}/` | 管理员 | 更新资产主数据，必须提交当前 `version`；并发过期返回 `409`，停用存在活动告警或工单的资产返回 `409` |
| `GET` | `/gis/features/` | 登录 | 返回 WGS84 GeoJSON FeatureCollection；支持 `layerType`、`bbox=minLon,minLat,maxLon,maxLat`；默认仅 `published`，管理员可用 `status=all` |
| `POST` | `/gis/features/` | 管理员 | 新建受控空间对象；仅接受 Point、LineString、Polygon 与 EPSG:4326，写审计 |
| `PATCH` | `/gis/features/{id}/` | 管理员 | 提交 `version` 更新空间对象；发布必须同时具备 `verifiedAt` 与 `sourceReference` |
| `POST` | `/gis/features/import/` | 管理员 | 原子导入 1–100 个 GeoJSON Feature；任一对象无效或编码冲突则整批回滚 |
| `GET` | `/hardware-bindings/` | 登录 | 查询资产的硬件通信契约；支持 `assetCode`、分页 |
| `POST` | `/hardware-bindings/` | 管理员 | 为活动资产预留 MQTT、HTTP、串口网关或人工登记接口，写审计 |
| `PATCH` | `/hardware-bindings/{id}/` | 管理员 | 提交 `version` 更新端点、期望心跳或接入状态；资产绑定不可迁移 |
| `GET` | `/alerts/` | 登录 | `status`、`severity`、`openedFrom`、`openedTo`、`page`、`pageSize` |
| `POST` | `/alerts/{id}/acknowledge/` | 管理员/运维员 | 确认待处理告警 |
| `POST` | `/alerts/{id}/work-order/` | 管理员/运维员 | 从告警创建关联工单；严重告警默认 4 小时、其他告警默认 24 小时处置时限 |
| `GET` | `/work-orders/` | 登录 | `status`、`search`、`updatedFrom`、`updatedTo`、`page`、`pageSize` |
| `POST` | `/work-orders/` | 管理员/运维员 | 新建 `{ assetCode, title, description?, priority? }`；可提供 `Idempotency-Key` 防止重试重复建单。后端按优先级写入处置时限：低 72 小时、普通 48 小时、高 24 小时、紧急 4 小时 |
| `POST` | `/work-orders/{id}/transition/` | 管理员/运维员 | 流转 `{ to, version? }`；提供 `version` 时启用乐观锁，完成工单必须管理员复核 |
| `GET` | `/telemetry/` | 登录 | `assetCode`、`metricKey`、`quality`、`recordedFrom`、`recordedTo`、`page`、`pageSize`；按业务采集时间倒序返回 |
| `GET` | `/telemetry/summary/` | 登录 | 复用遥测筛选条件，返回样本数、最小值、最大值、平均值、时间范围、质量分布和最新样本 |
| `POST` | `/telemetry/` | 管理员/运维员/采集密钥 | 批量写入 1–100 条可信遥测；按 `eventId` 幂等，刷新通信心跳并驱动阈值告警和资产状态联动；`X-Ingest-Key` 仅在此端点启用 |
| `GET` | `/thresholds/` | 登录 | 查询阈值策略 |
| `PUT` | `/thresholds/{key}/` | 管理员 | 更新 `{ warning, alarm, version }`，使用乐观锁 |
| `GET` | `/audit/` | 登录 | `action`、`search`（动作、资源类型/编号或操作者邮箱）、`occurredFrom`、`occurredTo`、`page`、`pageSize` |
| `GET` | `/report-exports/` | 登录 | 导出操作记录 |
| `POST` | `/report-exports/` | 登录 | 创建 `{ report: alerts\|workOrders\|assets\|daily }`；可提供 `Idempotency-Key` 防止重复登记 |
| `GET` | `/report-exports/{id}/download/` | 创建者/管理员 | 返回创建时固化的 UTF-8 CSV 不可变快照；响应含 SHA-256，执行公式注入防护且不受前端分页限制 |

## 角色边界

| 操作 | 管理员 | 运维员 | 查看者 |
| --- | --- | --- | --- |
| 查询业务数据 | ✓ | ✓ | ✓ |
| 写入可信遥测 | ✓ | ✓ | — |
| 确认告警 | ✓ | ✓ | — |
| 新建/流转工单 | ✓ | ✓ | — |
| 完成工单复核 | ✓ | — | — |
| 修改阈值 | ✓ | — | — |
| 新建/修改/停用资产主数据 | ✓ | — | — |
| 导入、审核与发布 GIS 空间对象 | ✓ | — | — |
| 维护硬件通信绑定契约 | ✓ | — | — |
| 导出报表 | ✓ | ✓ | ✓ |

任何未列出的写操作默认拒绝，后端权限校验是最终边界，前端按钮隐藏仅用于改善使用体验。

机器采集主体不属于人员角色：`X-Ingest-Key` 只在 `/telemetry/` 上安装认证器，只允许 `POST`，不能读取业务数据、确认告警、创建工单或访问管理接口。

## 遥测批量写入与自动规则

`POST /telemetry/` 接受以下结构；整个批次在同一事务内校验与写入，任意未知/停用资产、单位不一致或幂等冲突都会拒绝整批数据，不产生部分提交：

```json
{
  "readings": [
    {
      "eventId": "sim:ENV-01:temperature:20260827T160000Z",
      "assetCode": "ENV-01",
      "metricKey": "temperature",
      "metric": "环境温度",
      "value": 30.2,
      "unit": "°C",
      "quality": "good",
      "recordedAt": "2026-08-27T16:00:00+08:00"
    }
  ]
}
```

- `eventId` 全局唯一。相同事件和相同数据重试返回已有记录；复用事件号提交不同数据返回 `409 idempotency_conflict`。
- `recordedAt` 不得早于当前时间 30 天，允许最多 5 分钟时钟漂移；数值必须有限且位于安全输入范围。
- 只有 `quality=good` 的读数参与规则计算。指标存在阈值时，单位必须与阈值配置一致。
- 首次越过预警线创建自动告警；越过报警线只升级现有活动告警，不重复建告警；恢复到预警线以下时自动解决告警并重算资产状态。
- 返回 `created`、`duplicates`、`rules` 和本批次 `items`；所有自动创建、升级、恢复和批次写入均写审计日志。

历史查询以 `recordedAt` 作为业务时间、以记录编号作为稳定次序补充，避免延迟到达的数据被误判为最新样本。`recordedFrom` 晚于 `recordedTo`、时间格式无效或筛选枚举无效时返回统一 `400 validation_error`；无匹配数据时汇总字段返回 `null` 或零值，不伪造统计结果。汇总结果通过 `comparable` 标明当前数据是否属于同一指标和单位；混合量纲时不计算均值、最小值和最大值。
