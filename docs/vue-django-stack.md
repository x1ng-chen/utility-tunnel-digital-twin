# Vue 3 + Django 标准软件栈

本仓库新增一套可独立部署的标准前后端实现，用于把软件平台从浏览器演示逐步切换为企业级应用：

- `frontend/`：Vue 3、Vite、TypeScript、Pinia、Vue Router、Axios；通过 `VITE_API_BASE_URL` 使用唯一的 Django API 数据源。
- `backend/`：Django 5.2 LTS、Django REST Framework、Token Bearer 认证、RBAC、PostgreSQL（未配置时本地回退 SQLite）。
- `frontend/`、`backend/`、`firmware/`、`deploy/` 与既有规划文档构成当前交付基线；旧版 React/Node 兼容代码已归档移除，历史版本可通过 Git 提交记录追溯。

## 本地运行

### Django API

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install --require-hashes -r requirements.lock
Copy-Item .env.example .env
python manage.py migrate
python manage.py seed_demo
python manage.py runserver 127.0.0.1:8000
```

`seed_demo` 创建固定的本地演示管理员账号 `admin`，密码为 `123`。该弱口令只供隔离的本地演示和自动化回归使用，命令在生产环境中会直接拒绝执行。生产账号应通过审批与一次性密码设置链接创建，密钥、允许主机和 `DATABASE_URL` 必须从受控环境注入。

### API 安全与运行检查

- 人员账号的 Bearer Token 默认有效期 15 分钟（`API_TOKEN_TTL_SECONDS`），过期令牌会被拒绝并在下一次登录时轮换。IoTDA 网关使用仅在 `POST /api/telemetry/` 启用的 `DJANGO_INGEST_API_KEY`，不能读取业务数据或执行人员操作，也不持有人类账号密码。
- 登录、注册申请和一次性密码设置分别按客户端地址限流（`LOGIN_RATE_LIMIT`、`REGISTRATION_RATE_LIMIT`、`PASSWORD_SETUP_RATE_LIMIT`），默认只使用 TCP 对端地址；仅在反向代理已覆盖并可信时设置 `DJANGO_TRUST_PROXY_HEADERS=true` 以读取 `X-Forwarded-For`。多实例部署时应把 Django 缓存切换到共享 DatabaseCache、Redis 或 Memcached，并在网关再设置一层限流。
- `DJANGO_ENV` 只接受 `development`、`test` 或 `production`；生产环境会强制关闭调试、拒绝 SQLite 回退，并要求 PostgreSQL `sslmode=require`/`verify-ca`/`verify-full`，同时启用 HTTPS 重定向、HSTS 与安全 Cookie。生产环境的 `CORS_ALLOWED_ORIGINS`、`DJANGO_CSRF_TRUSTED_ORIGINS` 必须精确填写正式 HTTPS 前端 Origin，`DJANGO_ALLOWED_HOSTS` 不得使用通配符且共享缓存必须显式配置。
- `DATABASE_URL` 必须包含 PostgreSQL 主机、用户名和数据库名；`DB_CONN_MAX_AGE` 必须为非负整数。配置不完整或格式错误时 Django 会在启动阶段 fail fast。
- `GET /api/health/` 只表示进程存活；`GET /api/ready/` 会执行数据库探针，返回 503 时禁止流量切入。
- 所有响应包含 `X-Request-Id`，该值会写入操作审计，便于跨前端、网关和 API 排障。
- Django 请求日志使用标准库输出 JSON（时间、级别、路径、状态码、耗时和 request ID），可直接接入华为云日志服务；不在日志中记录密码、Bearer Token 或数据库连接串。

### Vue 3 前端

```powershell
cd frontend
npm install
npm run dev
```

复制 `.env.example` 为 `.env.local` 后设置 `VITE_API_BASE_URL=http://127.0.0.1:8000/api`。登录页只连接该构建时地址；人员令牌保存在当前浏览器会话的 `sessionStorage`，所有写操作仍由服务端 RBAC 再次校验。前端在可见页面下每 2 秒刷新实时摘要；服务端在线判定以硬件绑定心跳为准。CSV 在创建导出记录时固化为带 SHA-256 的不可变快照，会中和公式前缀且不受页面分页限制。

## 质量门禁

```powershell
cd frontend
npm run test
npm run build

cd ..\backend
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test
```

当前 Django API 测试覆盖登录/令牌过期、存活与就绪探针、RBAC 写权限、分页筛选、告警、工单、阈值、审计和报表导出。数据库索引迁移必须随版本一起发布，CI 会通过 `makemigrations --check --dry-run` 阻断遗漏迁移。

接口统一返回 JSON 错误对象（`error`、`message`），关键资源使用分页、版本号和审计日志；阈值更新采用乐观并发控制，工单状态由服务端状态机约束。
