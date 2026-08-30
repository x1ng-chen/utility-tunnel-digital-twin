# 部署与恢复手册

> 适用范围：P1 软件 API + PostgreSQL + P3 演示交付。所有真实密码和连接串只放在托管平台的密钥管理界面。

> 正式云端目标为华为云。服务分层、网络边界、IoTDA 对接与上线检查见 [华为云部署方案](华为云部署方案.md)；本手册保留应用和数据库的通用发布、恢复步骤。

## 1. 托管 PostgreSQL

1. 创建 PostgreSQL 18 实例和数据库 `utility_tunnel`，启用 TLS、每日自动备份与至少 7 天保留。
2. 使用 Django 迁移身份（数据库所有者或专用发布账号）运行：

```bash
cd backend
python -m pip install -r requirements.txt
python manage.py migrate
python manage.py seed_demo
```

3. 迁移完成后，以数据库所有者身份在平台 SQL 控制台执行 [`deploy/postgres/provision.sql`](../deploy/postgres/provision.sql)，为 Django API 创建 `ut_runtime` 最小权限账号。脚本会撤销通用表写入权限，仅授予 `backend/operations/views.py` 当前 ORM 路径所需的列级权限。
4. 将 API 的 `DATABASE_URL` 配置为 `ut_runtime` 的 TLS 连接串。运行时账号不应拥有 `CREATE`、`DROP`、数据库管理员或角色管理权限；后续新增表或写入列时，必须随发布 SQL 显式审查并补充授权。

## 2. API 环境

按 `backend/.env.example` 创建部署环境变量：

- `DATABASE_URL`：只允许 TLS 的运行时账号连接串；
- `DJANGO_SECRET_KEY`：每个环境独立、至少 32 个随机字符；
- `DJANGO_ENV=production`、`DJANGO_ALLOWED_HOSTS` 和 `CORS_ALLOWED_ORIGINS`；
- `DJANGO_CSRF_TRUSTED_ORIGINS`：与前端 HTTPS Origin 精确匹配；生产环境不得使用开发机 Origin；
- `DJANGO_SECURE_SSL_REDIRECT=true`、`DJANGO_ENABLE_HSTS=true` 与 `DJANGO_TRUST_PROXY_SSL=true`：本项目的 Nginx TLS 终止架构必须信任 `X-Forwarded-Proto`，避免 HTTPS 重定向循环；
- `DATABASE_URL`：`ut_runtime` 的 PostgreSQL TLS 连接串；
- `API_TOKEN_TTL_SECONDS`、`LOGIN_RATE_LIMIT` 与 `PASSWORD_CHANGE_RATE_LIMIT`：按安全策略设置；登录和已认证改密分别限流，避免登录保护被日常改密操作消耗；
- `DJANGO_MAX_REQUEST_BYTES` 与 `DJANGO_MAX_REQUEST_FIELDS`：限制单次请求体大小和字段数量，防止异常请求耗尽内存；
- `TWIN_MODEL_MAX_BYTES`：三维 GLB 上传上限，默认 32 MB；反向代理请求体上限必须不小于该值；
- `DJANGO_CACHE_BACKEND` 与 `DJANGO_CACHE_LOCATION`：登录限流必须使用跨进程共享缓存；如果使用 Django 内置 `DatabaseCache`，迁移后执行一次 `python manage.py createcachetable <cache_table>`；
- `SEED_ADMIN_*`：仅首次种子初始化使用，之后从运行环境移除。

启动后依次检查：

```text
GET /api/health/   # 进程存活
GET /api/ready/    # 数据库可用
POST /api/auth/login/
```

上线前在 ECS 应用目录执行一次生产预检（该命令不修改业务数据）：

```bash
cd backend
python manage.py production_preflight
```

预检会拒绝非生产配置、非 PostgreSQL/TLS 连接、未启用 HTTPS/HSTS、进程内缓存和未执行迁移，并执行一次 `SELECT 1` 数据库探针。CI 会先执行迁移再运行预检；本地仅做数据库连通性探针时可显式使用 `--allow-non-production --skip-migrations`，生产环境不允许跳过迁移检查。

## 3. 前端

部署 `frontend` 后设置公开变量 `VITE_API_BASE_URL=https://<你的-api-domain>/api`；这只能是 API 地址，绝不能放入数据库 URL、密码或 Token。若未设置，站点默认使用本地演示模式。Django 的 `CORS_ALLOWED_ORIGINS` 必须精确允许该前端 Origin。

### 容器化制品

仓库提供无需在开发电脑额外安装服务的部署制品：`deploy/containers/Dockerfile.api`、`Dockerfile.web` 与 `docker-compose.production.yml`。它们以非 root API 用户、只读文件系统、内部 API 网络和回环 Web 端口为默认安全边界；真实 RDS 始终由外部托管，不会被 Compose 以数据卷方式创建。

在具备 Docker 和华为云环境变量的 ECS 上，按 [容器部署说明](../deploy/containers/README.md) 执行。构建完成后必须在 API 容器内运行：

```bash
python manage.py production_preflight
python manage.py data_governance_report --format=json
```

第二条命令仅生成遥测、审计与导出记录的保留期审查报告，不会删除任何业务数据。实际数据清理必须由单独、经审批且带审计记录的发布执行。

## 4. 备份与恢复

- 日常：在托管 PostgreSQL 平台开启自动快照与时间点恢复，确认最近一次备份成功。
- 发布前：记录当前迁移版本 `SELECT app, name, applied FROM django_migrations ORDER BY applied;`。
- 手动导出（在装有 PostgreSQL 客户端的受控发布机）：`pg_dump --format=custom --no-owner --file=utility_tunnel.backup "$DATABASE_URL"`。
- 恢复演练：先恢复到**隔离的新实例**，用迁移身份运行 `python manage.py migrate`，再用运行时账号访问 `/api/ready/` 和执行只读验证。不得在未验证备份的生产库上直接恢复。

三维模型文件保存在容器持久卷 `twin_model_media`。模型卷与 PostgreSQL 必须作为同一恢复点备份，恢复后抽查数据库中使用中版本的 SHA-256 与文件是否一致。详细交付步骤见[三维模型发布与交付规范](./三维模型发布与交付.md)。

### Django API 数据库

Django 栈使用同一 `DATABASE_URL`，备份脚本不保存密码或备份文件到 Git：

```powershell
$env:DATABASE_URL = 'postgresql://<backup-user>:<password>@<host>:5432/utility_tunnel?sslmode=require'
.\deploy\postgres\backup-django.ps1
```

脚本生成 PostgreSQL custom-format 备份和 SHA-256 校验文件。恢复必须在隔离实例执行，并显式确认：

```powershell
.\deploy\postgres\restore-verify-django.ps1 `
  -BackupFile .\deploy\postgres\backups\utility-tunnel-django-<timestamp>.backup `
  -TargetDatabaseUrl 'postgresql://<restore-user>:<password>@<isolated-host>:5432/utility_tunnel?sslmode=require' `
  -ConfirmRestore
```

恢复验收标准：`pg_restore` 无错误、`operations_asset` 与 `django_migrations` 可查询、`GET /api/ready/` 返回 200、API 只读接口和登录接口通过 smoke test。不要在未验证的生产库上直接使用 `--clean`。

## 5. 回滚

本仓库迁移策略是前向修复：若发布失败，停止 API、恢复上一版应用，并创建新的补偿迁移；禁止在生产库手工删除已记录的迁移或执行未评审的破坏性 SQL。
