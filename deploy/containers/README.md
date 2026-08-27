# 容器化生产部署

本目录提供 Vue 3 + Django 主软件栈的生产制品定义。它不包含账号、密钥、数据库连接串或证书；这些只应放在华为云密钥管理、ECS 受控环境变量或 CI Secret 中。

## 发布顺序

1. 在 RDS 上以迁移身份执行 `python manage.py migrate` 与 `python manage.py seed_demo`（首次环境）。
2. 以数据库所有者执行 `deploy/postgres/provision.sql`，创建最小权限的 `ut_runtime`。
3. 在 ECS 的受控环境设置 `DJANGO_SECRET_KEY`、`DATABASE_URL`、Origin、共享缓存及版本号。
4. 构建并启动：`docker compose -f deploy/containers/docker-compose.production.yml up -d --build`。
5. 在 API 容器内运行 `python manage.py production_preflight`，然后通过 `/api/ready/` 验证数据库。
6. 由 ECS 外层 Nginx、ELB 或 CDN 终止 HTTPS 并转发到 `127.0.0.1:8080`；不要直接对公网暴露 API 容器端口。

## 运行边界

- `web` 容器仅公开本地回环端口，Django API 仅加入容器内部网络。
- API 使用非 root 用户、只读文件系统与临时 `/tmp`；数据库必须使用 TLS 与最小权限账号。
- Compose 文件不会启动数据库，避免把真实 RDS 密码、备份或数据卷混入应用部署目录。
- 容器镜像可在 GitHub Actions 构建验证；真实 ECS、RDS、证书、域名和密钥创建仍需要华为云账号权限。
