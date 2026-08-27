# 软件平台说明

## 已交付的软件演示

当前标准软件栈位于 `frontend/`（Vue 3）与 `backend/`（Django + DRF），同时支持两种明确的数据源：默认的浏览器本地演示模式，以及登录后使用 Django API 的正式数据模式。两种模式共用同一套业务对象和页面，避免分别维护互相矛盾的功能。`apps/web` 与 `services/api` 保留为迁移兼容基线，不是本阶段的主运行入口。

- **本地演示模式**：不接硬件、不开数据库即可运行；业务模拟数据只保存在当前页面会话内，刷新后重新加载安全种子数据，不会把演示记录上传或写入项目文件。
- **API 模式**：登录页选择“Django API”，输入已部署 API 的地址与账号。访问令牌只保存在当前浏览器会话的 `sessionStorage`，过期会自动清理身份并返回登录页；资产、告警、工单、阈值、遥测、导出登记和审计由 Django API 读取或写入 PostgreSQL（本地开发可回退 SQLite）。

| 模块 | 单一职责 | 已实现能力 |
| --- | --- | --- |
| 数字孪生 | 空间与资产状态展示 | 可配置区域与资产坐标、区域/设备点击定位、详情检查、异常高亮、关联告警跳转 |
| 告警中心 | 事件确认与来源关联 | 确认、按告警创建工单、状态计数、CSV 导出 |
| 工单中心 | 工作任务生命周期 | 手工创建、告警创建、派发/处置/复核/完成受控流转、自动闭环来源告警 |
| 设备台账 | 资产主数据检索 | 关键字、区域和状态筛选，实时更新时间，CSV 导出 |
| 数据洞察 | 运行统计与答辩资料 | 模拟遥测趋势、运行指标、告警/工单/资产/日报的 CSV 与 JSON 导出 |
| 审计追踪 | 关键业务可追溯 | 告警、工单、阈值、角色、导出等行为统一记录与检索 |
| 系统配置 | 规则维护 | 预警/报警阈值校验与版本递增 |

## 数据与闭环规则

前端使用 `frontend/src/stores/operations.ts` 作为唯一的数据模型和状态转换入口；`frontend/src/stores/auth.ts` 负责会话生命周期；`frontend/src/services/api.ts` 只负责 Django API 映射。它们共同覆盖资产、告警、工单、遥测、阈值、会话和审计记录，禁止由页面组件各自维护重复业务数据。

```text
模拟遥测 → 资产状态/孪生高亮
告警确认 → 审计
告警创建工单 → 来源关联 + 审计
工单 派发 → 处置 → 复核 → 完成 → 来源告警恢复 + 资产状态刷新 + 审计
阈值或角色变更 → 审计
报告导出 → 审计
```

工单不能跳过复核直接完成；同一告警不能重复建立来源工单；无权限动作即使绕过界面也会被状态转换器拒绝。

## 角色

| 角色 | 可执行操作 |
| --- | --- |
| 管理员 | 告警、工单、阈值、导出 |
| 运维员 | 告警、工单、导出 |
| 查看者 | 浏览和导出 |

本地模式下登录页可以选择演示角色；该角色只用于当前页面会话，不会上传。API 模式下角色来自服务端登录响应，服务端会再次执行权限校验，不能依赖前端做授权。

## 运行与质量检查

Vue 3 + Django 标准栈本地运行：

```powershell
cd frontend
npm ci
npm run dev

cd ..\backend
python manage.py migrate
python manage.py seed_demo
python manage.py runserver 127.0.0.1:8000
```

提交前执行：

```powershell
cd frontend
npm test
npm run build

cd ..\backend
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test
python -m compileall -q config operations
```

GitHub Actions 对 Vue 3 前端执行测试、类型检查、生产构建和高危依赖审计；对 Django 执行配置检查、迁移一致性、接口/RBAC 测试和字节码检查。上述命令均使用仓库已有工具，不需要硬件或新增运行时服务。

## 从演示数据迁移到 PostgreSQL

`backend` 已包含 Django 迁移、Token Bearer 认证、RBAC、资产、遥测、告警、工单、审计、阈值和导出记录。Vue 前端已经实现 API 客户端、登录、分页回读、会话过期清理和失败降级；不需要替换页面或重写业务对象。`services/api` 的 PostgreSQL 实现仅用于旧版兼容验证。

完整接口、权限和写入约束见 [API 契约](api-contract.md)。要在本地或托管环境启用它：

```powershell
cd backend
Copy-Item .env.example .env
# 填入 DATABASE_URL、DJANGO_SECRET_KEY、DJANGO_ALLOWED_HOSTS 与种子账号后：
python manage.py migrate
python manage.py seed_demo
python manage.py runserver 127.0.0.1:8000
```

随后可在 `frontend/.env.local` 设置 `VITE_API_BASE_URL`，或直接在界面中输入 API 地址。部署时必须把前端的真实站点地址加入 API 的 `CORS_ALLOWED_ORIGINS`。

不应把数据库连接串、Django 密钥或真实账号提交到仓库。使用 `backend/.env.example` 创建本地 `.env`，并由托管数据库平台提供连接字符串。

## 发布制品与数据治理

`deploy/containers/` 提供面向 ECS 的 Vue 静态站与 Django API 容器制品；容器运行时从受控环境注入密钥，API 以非 root 用户运行且不公开容器内部端口。数据保留期先通过 `python manage.py data_governance_report --format=json` 进行只读盘点；审计、遥测或导出记录的真实清理必须走单独的审批、备份和审计流程。

## 验收边界

本版本验证软件业务流程，不代表工业控制或生命安全系统。模拟遥测、阈值和告警仅用于答辩演示，不能直接用于真实管廊或控制设备。
