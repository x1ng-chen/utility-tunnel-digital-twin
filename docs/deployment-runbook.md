# 部署与恢复手册

> 适用范围：P1 软件 API + PostgreSQL + P3 演示交付。所有真实密码和连接串只放在托管平台的密钥管理界面。

> 正式云端目标为华为云。服务分层、网络边界、IoTDA 对接与上线检查见 [华为云部署方案](华为云部署方案.md)；本手册保留应用和数据库的通用发布、恢复步骤。

## 1. 托管 PostgreSQL

1. 创建 PostgreSQL 18 实例和数据库 `utility_tunnel`，启用 TLS、每日自动备份与至少 7 天保留。
2. 使用迁移身份（数据库所有者或专用发布账号）运行：

```bash
cd services/api
npm ci
npm run migration:check
npm run migrate
npm run seed
```

3. 迁移完成后，以数据库所有者身份在平台 SQL 控制台执行 [`deploy/postgres/provision.sql`](../deploy/postgres/provision.sql)，为 API 创建 `ut_runtime` 最小权限账号。脚本会撤销通用表写入权限，仅授予 API 当前 SQL 路径所需的列级权限。
4. 将 API 的 `DATABASE_URL` 配置为 `ut_runtime` 的 TLS 连接串。运行时账号不应拥有 `CREATE`、`DROP`、数据库管理员或角色管理权限；后续新增表或写入列时，必须随发布 SQL 显式审查并补充授权。

## 2. API 环境

按 `services/api/.env.example` 创建部署环境变量：

- `DATABASE_URL`：只允许 TLS 的运行时账号连接串；
- `JWT_SECRET`：每个环境独立、至少 32 个随机字符；
- `WEB_ORIGIN`：完整的前端站点 Origin；
- `NODE_ENV=production` 与 `LOG_LEVEL=info`；
- `SEED_ADMIN_*`：仅首次种子初始化使用，之后从运行环境移除。

启动后依次检查：

```text
GET /v1/health   # 进程存活
GET /v1/ready    # 数据库可用
POST /v1/auth/login
```

## 3. 前端

部署 `apps/web` 后设置公开变量 `NEXT_PUBLIC_API_BASE_URL=https://<你的-api-domain>`；这只能是 API 地址，绝不能放入数据库 URL、密码或 JWT。若未设置，站点默认使用本地演示模式。API 的 `WEB_ORIGIN` 必须精确允许该前端 Origin。

## 4. 备份与恢复

- 日常：在托管 PostgreSQL 平台开启自动快照与时间点恢复，确认最近一次备份成功。
- 发布前：记录当前迁移版本 `SELECT * FROM schema_migration ORDER BY applied_at;`。
- 手动导出（在装有 PostgreSQL 客户端的受控发布机）：`pg_dump --format=custom --no-owner --file=utility_tunnel.backup "$DATABASE_URL"`。
- 恢复演练：先恢复到**隔离的新实例**，用迁移身份运行 `npm run migrate`，再用运行时账号访问 `/v1/ready` 和执行只读验证。不得在未验证备份的生产库上直接恢复。

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
