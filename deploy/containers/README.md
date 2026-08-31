# 容器化生产部署

本目录提供 Vue 3 + Django 主软件栈的生产制品定义。它不包含账号、密钥、数据库连接串或证书；这些只应放在华为云密钥管理、ECS 受控环境变量或 CI Secret 中。

## 发布顺序

1. 在 RDS 上以迁移身份执行 `python manage.py migrate`；生产环境严禁执行 `seed_demo`，首个管理员使用受控终端运行 `python manage.py createsuperuser` 创建。
2. 以数据库所有者执行 `deploy/postgres/provision.sql`，创建最小权限的 `ut_runtime`。
3. 在 ECS 的受控环境设置 `DJANGO_SECRET_KEY`、`DATABASE_URL`、Origin、共享缓存及版本号。
4. 构建并启动：`docker compose -f deploy/containers/docker-compose.production.yml up -d --build`。
5. 在 API 容器内运行 `python manage.py production_preflight`，然后通过 `/api/ready/` 验证数据库。
6. 由 ECS 外层 Nginx、ELB 或 CDN 终止 HTTPS 并转发到 `127.0.0.1:8080`；不要直接对公网暴露 API 容器端口。

## 运行边界

- `web` 容器仅公开本地回环端口，Django API 仅加入容器内部网络。
- `connectivity-monitor` 每 15 秒执行一次心跳巡检；超过硬件绑定约定周期会置离线并创建通信告警，遥测恢复后自动关闭告警。可通过 `DEVICE_OFFLINE_GRACE_MULTIPLIER`、`DEVICE_OFFLINE_MIN_GRACE_SECONDS` 和 `CONNECTIVITY_RECONCILE_INTERVAL_SECONDS` 调整。
- API 使用非 root 用户、只读文件系统与临时 `/tmp`；数据库必须使用 TLS 与最小权限账号。
- 已校验的 GLB 模型保存在 `twin_model_media` 持久卷；部署迁移、备份和恢复时必须与 PostgreSQL 版本元数据保持同一恢复点。
- Nginx 与 Django 默认允许最大 32 MB 的模型文件（代理层预留 34 MB 请求体）；调整 `TWIN_MODEL_MAX_BYTES` 时必须同步代理层上限。
- Compose 文件不会启动数据库，避免把真实 RDS 密码、备份或数据卷混入应用部署目录。
- 容器镜像可在 GitHub Actions 构建验证；真实 ECS、RDS、证书、域名和密钥创建仍需要华为云账号权限。
