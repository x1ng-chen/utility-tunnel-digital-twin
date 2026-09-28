# 部署与恢复手册

> 2026-09-28：本手册是部署步骤，不是生产部署已完成的证明。先按 [版本索引](项目当前状态.md)选择并冻结代码。若部署含 AI 助手的功能分支，按 [AI 接入](AI助手接入.md)仅在服务端配置密钥并重启 API；AI 需外网，核心本地业务不依赖它。当前密钥与线上调用未在本次文档核对中验证。

> 适用范围：P1 软件 API + PostgreSQL + P3 演示交付。所有真实密码和连接串只放在托管平台的密钥管理界面。

> 正式云端目标为华为云。服务分层、网络边界、IoTDA 对接与上线检查见 [华为云部署方案](华为云部署方案.md)；本手册保留应用和数据库的通用发布、恢复步骤。

## 1. 托管 PostgreSQL

1. 创建 **PostgreSQL 16** 实例和数据库 `utility_tunnel`，启用 TLS、每日自动备份与至少 7 天保留。当前 Django 模型把受控 GIS 几何保存为经过校验的 WGS84 GeoJSON/JSONB，**不依赖 PostGIS**；不得为本版本的应用运行 `CREATE EXTENSION postgis`，也不得把扩展创建权限授予 `ut_runtime`。若后续经评审的迁移确实引入 GIS 空间索引或拓扑查询，再在 PostgreSQL 16 兼容的托管实例中单独启用 PostGIS，并更新迁移、最小权限 SQL 和恢复演练。
2. 使用 Django 迁移身份（数据库所有者或专用发布账号）运行：

```bash
cd backend
python -m pip install --require-hashes -r requirements.lock
python manage.py migrate
python manage.py createsuperuser
```

> 生产环境严禁执行 `python manage.py seed_demo`。首个管理员只能在受控终端通过 `createsuperuser` 或已审批的账号开通流程创建；演示种子仅限本地开发和隔离自动化数据库。

3. 迁移完成并创建首个受控管理员后，以数据库所有者身份在平台 SQL 控制台执行 [`deploy/postgres/provision.sql`](../deploy/postgres/provision.sql)，为 Django API 创建 `ut_runtime` 最小权限账号。脚本会撤销通用表写入权限，仅授予 `backend/operations/views.py` 当前 ORM 路径所需的列级权限。
4. 将 API 的 `DATABASE_URL` 配置为 `ut_runtime` 的 TLS 连接串。运行时账号不应拥有 `CREATE`、`DROP`、数据库管理员或角色管理权限；后续新增表或写入列时，必须随发布 SQL 显式审查并补充授权。

## 2. API 环境

按 `backend/.env.example` 创建部署环境变量：

- `DATABASE_URL`：只允许 TLS 的运行时账号连接串；
- `DJANGO_SECRET_KEY`：每个环境独立、至少 32 个随机字符；
- `DJANGO_ENV=production`、`DJANGO_ALLOWED_HOSTS` 和 `CORS_ALLOWED_ORIGINS`；`DJANGO_ALLOWED_HOSTS` 只能填写精确的公开域名/IP（不含协议、不得使用 `*`），首项作为 API 容器就绪检查的 `Host` 头。健康检查仍连接容器内 `127.0.0.1`，不要为了探针而把 `localhost` 或任意主机加入公开白名单；
- `DJANGO_CSRF_TRUSTED_ORIGINS`：与前端 HTTPS Origin 精确匹配；生产环境不得使用开发机 Origin；
- `DJANGO_SECURE_SSL_REDIRECT=true`、`DJANGO_ENABLE_HSTS=true` 与 `DJANGO_TRUST_PROXY_SSL=true`：在本项目的固定链路“公网 TLS 边缘代理 → 回环 `127.0.0.1:8080` 内层 Nginx → Docker 内部 Django”中启用。内层 Nginx 不转发请求携带的 `X-Forwarded-Proto`，而是在受限回环跳点固定生成 `https` 后再交给 Django，避免任意客户端伪造该头造成安全请求误判；
- `DJANGO_TRUST_PROXY_HEADERS=false`：保持关闭。当前部署并未实现可验证来源的客户端 IP 传递，不能因为启用了 HTTPS 代理信任就同时信任用户可伪造的 `X-Forwarded-For`；如确需基于真实客户端地址限流，必须另行评审边缘代理源地址限制、头部清洗和 API 中的受信任代理策略；
- `CONNECTIVITY_MONITOR_TOKEN`：由密钥管理服务注入、至少 32 个随机字符。独立监测容器只可经 Docker 内网以该令牌请求 API 进程执行巡检；该接口不经公网 Nginx 暴露。监测命令和 API 健康检查均会在受控内部请求中显式标注 `X-Forwarded-Proto: https`，以避免 HTTPS 强制跳转到无 TLS 的容器端口；`CONNECTIVITY_RECONCILE_INTERVAL_SECONDS` 默认 15，允许范围 5–3600 秒；
- `DATABASE_URL`：`ut_runtime` 的 PostgreSQL TLS 连接串；
- `API_TOKEN_TTL_SECONDS`、`API_TOKEN_RENEWAL_WINDOW_SECONDS`、`LOGIN_RATE_LIMIT`、`REGISTRATION_RATE_LIMIT`、`PASSWORD_SETUP_RATE_LIMIT` 与 `PASSWORD_CHANGE_RATE_LIMIT`：按安全策略设置；人员令牌在临近过期时于重新登录中提前轮换，登录、注册申请、一次性密码设置和已认证改密分别限流，避免不同入口互相消耗安全预算；
- `DJANGO_MAX_REQUEST_BYTES` 与 `DJANGO_MAX_REQUEST_FIELDS`：限制单次请求体大小和字段数量，防止异常请求耗尽内存；
- `TWIN_MODEL_MAX_BYTES`：三维 GLB 上传上限，默认 32 MB；反向代理请求体上限必须不小于该值；
- `DJANGO_CACHE_BACKEND` 与 `DJANGO_CACHE_LOCATION`：登录限流必须使用跨进程共享缓存；如果使用 Django 内置 `DatabaseCache`，迁移后执行一次 `python manage.py createcachetable <cache_table>`；
- `SEED_ADMIN_*`：生产环境不得设置或使用；它们只允许出现在本地开发或隔离自动化数据库的演示种子配置中。

启动后依次检查：

```text
GET /api/health/   # 进程存活
GET /api/ready/    # 数据库可用
POST /api/auth/login/
```

### HTTPS 代理信任边界

`web` 服务只发布到宿主机回环地址 `127.0.0.1:8080`。公网入口必须由同一受控主机上的 TLS 终止代理、负载均衡器或 CDN 接收，并在到达该回环端口前完成 HTTP→HTTPS 重定向；禁止将 `8080`、API 容器 `8000` 或 Docker 网络直接暴露给公网。外层代理应清除客户端自带的 `X-Forwarded-Proto`、`X-Forwarded-For` 与 `X-Real-IP`，自行生成所需的日志/追踪头。内层 Nginx 只把自己生成的 `X-Forwarded-Proto: https` 发送给 Django，因此 Django 信任的是受网络边界保护的内部代理，而不是浏览器提交的任意头部。

上线前在 ECS 应用目录执行一次生产预检（该命令不修改业务数据）：

```bash
cd backend
python manage.py production_preflight
python manage.py release_preflight --clean-test-data --require-model --format=json
```

第一条预检会拒绝非生产配置、非 PostgreSQL/TLS 连接、未启用 HTTPS/HSTS、进程内缓存和未执行迁移，并执行一次 `SELECT 1` 数据库探针。第二条只清理自动化测试专用命名空间，随后确认没有测试账号、测试空间对象、临时资产和测试模型，并要求存在兼容且已启用的三维模型；它不会删除普通业务数据。CI 会先执行迁移再运行预检；本地仅做数据库连通性探针时可显式使用 `--allow-non-production --skip-migrations`，生产环境不允许跳过迁移检查。

## 3. 前端

构建 `frontend` 时设置公开变量 `VITE_API_BASE_URL=https://<你的-api-domain>/api`；这只能是 API 地址，绝不能放入数据库 URL、密码或 Token。未设置时仅回退到本机开发地址，不提供浏览器演示数据。Django 的 `CORS_ALLOWED_ORIGINS` 必须精确允许该前端 Origin。

### 容器化制品

仓库提供无需在开发电脑额外安装服务的部署制品：`deploy/containers/Dockerfile.api`、`Dockerfile.web` 与 `docker-compose.production.yml`。它们以非 root API 用户、只读文件系统、内部 API 网络和回环 Web 端口为默认安全边界；真实 RDS 始终由外部托管，不会被 Compose 以数据卷方式创建。编排中的 `connectivity-monitor` 默认每 15 秒请求 API 进程运行心跳巡检，把超时绑定转为离线状态和通信告警；它不直接写业务库，因此告警与设备状态会在同一 API 进程的 WebSocket 事件总线中发布。此保证只适用于当前单 API 进程部署；横向扩容前必须先实施持久 outbox 与跨进程消息代理。

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
