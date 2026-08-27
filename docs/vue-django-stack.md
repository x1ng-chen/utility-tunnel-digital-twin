# Vue 3 + Django 标准软件栈

本仓库新增一套可独立部署的标准前后端实现，用于把软件平台从浏览器演示逐步切换为企业级应用：

- `frontend/`：Vue 3、Vite、TypeScript、Pinia、Vue Router、Axios；支持本地演示和 Django API 两种数据源。
- `backend/`：Django 4.2、Django REST Framework、Token Bearer 认证、RBAC、PostgreSQL（未配置时本地回退 SQLite）。
- 原有 `apps/web/`、`services/api/`、`firmware/`、`deploy/` 和既有规划文档保持不变，便于平滑迁移和回滚。

## 本地运行

### Django API

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
python manage.py migrate
python manage.py seed_demo
python manage.py runserver 127.0.0.1:8000
```

默认演示账号由 `seed_demo` 创建，密码为 `demo-password-2026`。生产环境必须替换密码、密钥、允许主机和 `DATABASE_URL`。

### API 安全与运行检查

- Bearer Token 默认有效期 15 分钟（`API_TOKEN_TTL_SECONDS`），过期令牌会被拒绝并在下一次登录时轮换；生产环境建议使用 5–15 分钟并配合网关刷新策略。
- 登录接口按客户端地址限流（`LOGIN_RATE_LIMIT`，默认每分钟 10 次），默认只使用 TCP 对端地址；仅在反向代理已覆盖并可信时设置 `DJANGO_TRUST_PROXY_HEADERS=true` 以读取 `X-Forwarded-For`。多实例部署时应把 Django 缓存切换到共享 Redis/Memcached，并在网关再设置一层限流。
- `DJANGO_ENV=production` 会强制关闭调试、拒绝 SQLite 回退，并要求 PostgreSQL `sslmode=require`/`verify-ca`/`verify-full`，同时启用 HTTPS 重定向、HSTS 与安全 Cookie；`CORS_ALLOWED_ORIGINS` 必须精确填写正式前端 Origin。
- `GET /api/health/` 只表示进程存活；`GET /api/ready/` 会执行数据库探针，返回 503 时禁止流量切入。
- 所有响应包含 `X-Request-Id`，该值会写入操作审计，便于跨前端、网关和 API 排障。
- Django 请求日志使用标准库输出 JSON（时间、级别、路径、状态码、耗时和 request ID），可直接接入华为云日志服务；不在日志中记录密码、Bearer Token 或数据库连接串。

### Vue 3 前端

```powershell
cd frontend
npm install
npm run dev
```

复制 `.env.example` 为 `.env.local` 后可设置 `VITE_API_BASE_URL=http://127.0.0.1:8000/api`。登录页可切换“演示工作区”和“Django API”；API 模式的令牌只用于当前本地会话存储，所有写操作仍由服务端 RBAC 再次校验。

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
