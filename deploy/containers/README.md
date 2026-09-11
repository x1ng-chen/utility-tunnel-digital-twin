# 容器化生产部署

本目录提供 Vue 3 + Django 主软件栈的生产制品定义。它不包含账号、密钥、数据库连接串或证书；这些只应放在华为云密钥管理、ECS 受控环境变量或 CI Secret 中。

## 发布顺序

1. 在 PostgreSQL 16 RDS 上以迁移身份执行 `python manage.py migrate`；生产环境严禁执行 `seed_demo`，首个管理员使用受控终端运行 `python manage.py createsuperuser` 创建。当前 GIS 几何是经过校验的 WGS84 GeoJSON/JSONB，生产运行不需要 PostGIS；后续只有经评审迁移引入空间索引/拓扑能力时，才单独启用与 PostgreSQL 16 匹配的 PostGIS。
2. 以数据库所有者执行 `deploy/postgres/provision.sql`，创建最小权限的 `ut_runtime`。
3. 在 ECS 的受控环境设置 `DJANGO_SECRET_KEY`、`DATABASE_URL`、Origin、共享缓存及版本号。
4. 构建并启动：`docker compose -f deploy/containers/docker-compose.production.yml up -d --build`。
5. 在 API 容器内运行 `python manage.py production_preflight`，然后通过 `/api/ready/` 验证数据库。
6. 由 ECS 外层 Nginx、ELB 或 CDN 终止 HTTPS 并转发到 `127.0.0.1:8080`；不要直接对公网暴露 API 容器端口。

## 运行边界

- API 使用单进程 Daphne ASGI，同时提供 HTTP 与 `/ws/events/`。本地和 CI 的 `manage.py runserver` 由 `daphne` 接管；更新依赖与代码后，旧 WSGI 服务需人工确认后重启，脚本不会强制停止已有服务。
- 当前实时事件缓冲区与 channel layer 仅在进程内共享；禁止增加 API 副本或另启动 WSGI worker 后仍假定推送完整。独立 `connectivity-monitor` 不直接写库：它通过 Docker 内网、携带专用高熵令牌调用 API 进程的巡检接口，因此本部署中的离线/恢复事件会由持有 WebSocket 客户端的 API 进程发布。跨 API 副本、跨主机的持久事件与补读游标仍需独立 outbox/消息代理方案；只替换 Redis channel layer 不足以解决游标一致性。
- 外层 HTTPS 代理必须同样转发 `/ws/` 的 Upgrade/Connection，保留浏览器 Origin 和公开 Host；设置 `WEBSOCKET_ALLOWED_ORIGINS` 可收紧源站名单（默认沿用 CORS，生产仅接受 HTTPS Origin）。Nginx CSP 允许同公开 Host 的 `wss`，不开放任意 WebSocket 域名。
- HTTPS 信任链固定为“公网 TLS 边缘代理 → `127.0.0.1:8080` 内层 Nginx → Docker 内部 API”。外层必须阻止直接访问回环端口并清除客户端传入的 forwarding headers；内层 Nginx 只生成固定的 `X-Forwarded-Proto: https` 给 Django，绝不把请求中的同名头透传。`DJANGO_TRUST_PROXY_HEADERS` 保持 `false`，不能把 HTTPS 信任误扩展为对用户可伪造客户端 IP 的信任。
- `web` 容器仅公开本地回环端口，Django API 仅加入容器内部网络。
- `connectivity-monitor` 每 15 秒通过 Docker 内网调用 API 进程一次心跳巡检；`CONNECTIVITY_MONITOR_TOKEN` 必须由密钥管理服务注入且至少 32 字符，公网 Nginx 对该内部路由固定返回 404。超过硬件绑定约定周期会置离线并创建通信告警，遥测恢复后自动关闭告警。可通过 `DEVICE_OFFLINE_GRACE_MULTIPLIER`、`DEVICE_OFFLINE_MIN_GRACE_SECONDS` 和 `CONNECTIVITY_RECONCILE_INTERVAL_SECONDS` 调整。
- API 使用非 root 用户、只读文件系统与临时 `/tmp`；数据库必须使用 TLS 与最小权限账号。
- 已校验的 GLB 模型保存在 `twin_model_media` 持久卷；部署迁移、备份和恢复时必须与 PostgreSQL 版本元数据保持同一恢复点。
- Nginx 与 Django 默认允许最大 32 MB 的模型文件（代理层预留 34 MB 请求体）；调整 `TWIN_MODEL_MAX_BYTES` 时必须同步代理层上限。
- Compose 文件不会启动数据库，避免把真实 RDS 密码、备份或数据卷混入应用部署目录。
- 容器镜像可在 GitHub Actions 构建验证；真实 ECS、RDS、证书、域名和密钥创建仍需要华为云账号权限。
