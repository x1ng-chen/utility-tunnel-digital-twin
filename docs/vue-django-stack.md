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

接口统一返回 JSON 错误对象（`error`、`message`），关键资源使用分页、版本号和审计日志；阈值更新采用乐观并发控制，工单状态由服务端状态机约束。
