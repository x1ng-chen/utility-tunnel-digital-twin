# 软件质量门禁与回归记录

本文件记录 Vue 3 + Django 软件栈在不接硬件、不增加项目运行时依赖前提下的企业级验收入口。

## 自动门禁

```powershell
cd frontend
npm ci
npm test
npm run build
npm audit --omit=dev --audit-level=high

cd ..\backend
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test
python -m compileall -q config operations
```

自动门禁覆盖前端状态机与构建、依赖高危漏洞、Django 配置、数据库迁移一致性、认证令牌、限流、就绪探针、RBAC、告警、工单、阈值、审计、报表和请求 ID。

Django 运行日志为依赖无关的 JSON 结构，包含请求耗时和关联 ID；平台侧可按 `status_code >= 500` 建立异常告警，按 `duration_ms` 建立延迟指标。

## 浏览器端回归

使用当前环境已有的 Playwright CLI（通过 `npx --yes --package @playwright/cli playwright-cli` 调用，不写入项目依赖）执行以下验收路径：

1. 打开前端登录页，使用演示工作区进入运行总览。
2. 进入设备台账，确认四个空间节点渲染；点击 `SEEP-W01`，详情面板应显示 `关注`、坐标 `70, 68`、1 条待处置告警和 1 个关联工单。
3. 搜索不存在的编码，确认地图节点和详情区进入空态；清空搜索后列表恢复。
4. 退出，切换 Django API，使用 `operator@example.com / demo-password-2026` 登录；确认仪表盘显示 `Django API`、审计流出现 `auth.login`。
5. 检查浏览器控制台，Errors 和 Warnings 必须为 0。

## 发布前检查

- `/api/health/` 返回 200 仅代表进程存活；`/api/ready/` 返回 200 才允许接收流量。
- 生产环境必须设置不少于 32 位的 `DJANGO_SECRET_KEY`、HTTPS、精确 `CORS_ALLOWED_ORIGINS`、数据库 TLS 和共享缓存。
- 令牌有效期、登录限流、请求 ID 和审计日志应在部署环境变量中确认；不得把 `.env`、备份文件或密码提交到仓库。
- 数据库发布前执行 `deploy/postgres/backup-django.ps1`，恢复演练使用隔离目标和 `restore-verify-django.ps1 -ConfirmRestore`。
