# 软件质量门禁与回归记录

本文件记录 Vue 3 + Django 软件栈在不接硬件、不增加项目运行时依赖前提下的企业级验收入口。

## 自动门禁

仓库级安全扫描可直接执行：

```powershell
node tools/quality-scan.mjs
```

该扫描检查所有 Git 跟踪及未忽略的工作区文本文件，拒绝提交真实 `.env`、本地 `secrets.*` 配置、私钥和常见云平台令牌；大体积二进制和依赖目录不会被读取。GitHub Actions 会在 Vue/Django 工作流中自动执行。

```powershell
node tools/check-postgres-policy.mjs
node tools/check-twin-model-artifacts.mjs
```

该检查验证 PostgreSQL `ut_runtime` 账号的最小权限、管理员用户生命周期字段、Token/用户序列权限和占位符保护，防止正式环境授权脚本与 Django API 实际写入路径不一致。

```powershell
cd frontend
npm ci
npm test
npm run build
npm audit --registry=https://registry.npmjs.org --omit=dev --audit-level=high

cd ..\backend
pip install --require-hashes -r requirements.lock
pip install --require-hashes -r requirements-audit.lock
pip-audit --disable-pip --require-hashes -r requirements.lock
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test
python -m compileall -q config operations
python manage.py data_governance_report --format=json
```

自动门禁覆盖前端状态机与构建、npm/Python 依赖漏洞、Django 配置、数据库迁移一致性、认证令牌、限流、就绪探针、RBAC、告警、工单、阈值、审计、报表和请求 ID。Django 运行基线为仍在安全支持周期内的 5.2 LTS。

数据库层同时约束“同一来源告警只能关联一张工单”和“阈值报警值必须大于预警值”；列表 API 支持 ISO-8601 时间范围筛选，避免把完整数据集下载到浏览器后再过滤。

Django 运行日志为依赖无关的 JSON 结构，包含请求耗时和关联 ID；平台侧可按 `status_code >= 500` 建立异常告警，按 `duration_ms` 建立延迟指标。

## 浏览器端回归

`.github/workflows/browser-e2e.yml` 已在 GitHub Actions 中使用临时浏览器运行器执行真实浏览器回归，不向开发电脑或项目依赖写入浏览器包。业务流程回归与多分辨率视觉巡检分别运行在独立的浏览器、数据库和服务进程中，避免三维 WebGL 场景与跨页面截图长时间串行运行造成资源污染；生产容器构建作为第三项独立门禁并行执行。该工作流会验证以下路径：

1. 启动本地 Django、执行 `seed_demo`，使用正式账号密码登录并进入运行总览。
2. 进入设备台账，确认当前设备节点渲染；搜索并定位 `SEEP-W01`，核对水位传感器及接口信息；搜索不存在的编码后应进入空态。不要用旧示意坐标作为真实空间数据验收依据。
3. 进入 GIS 和三维孪生定位，在三维全屏中拖动设备栏并切换设备，确认正式 GLB、拖动状态和设备详情均正常。
4. 使用运维员确认告警、创建关联工单并推进处置流程；使用查看者确认写入与审批入口均不可见。
5. 提交注册申请、由管理员审批并交付一次性密码设置链接，完成密码设置后登录；同时验证管理员可维护资产和受控 GIS 坐标。
6. 使用测试环境种子账号登录，确认顶部数据服务已连接、审计页面能够读取登录记录。页面使用中文操作说明，不要求暴露 `auth.login` 等内部事件名。
7. 检查浏览器控制台，Errors 必须为 0；任一分组失败时分别上传 Playwright 失败现场及 Django/Vue 服务日志供定位。

本地使用 `tools/e2e/isolated_api.py` 创建独立临时数据库，测试进程设置 `E2E_API_URL=http://127.0.0.1:18000/api`；整批重跑前重新启动该测试服务。不要为运行回归而清理演示或生产数据库。详细步骤见 `tools/e2e/README.md`；CI 使用其新建数据库运行。

新增边界包括未知路由恢复、阈值版本冲突恢复、审批提交互斥、收起侧栏和 390/768 窄屏布局。截图必须人工检查：尺寸断言通过不代表文字无重叠、信息不误导或视觉体验已经验收。

首次推送后必须以该工作流绿色结果作为浏览器回归证据；未运行或失败不得写入“通过”。

## 发布前检查

- `/api/health/` 返回 200 仅代表进程存活；`/api/ready/` 返回 200 才允许接收流量。
- 生产环境必须设置不少于 32 位的 `DJANGO_SECRET_KEY`、显式 `DJANGO_ALLOWED_HOSTS`、HTTPS、精确的 `CORS_ALLOWED_ORIGINS` 与 `DJANGO_CSRF_TRUSTED_ORIGINS`、数据库 TLS 和跨进程共享缓存；Django 会拒绝生产环境的 LocMemCache。
- 生产环境的 CORS/CSRF Origin 必须使用 HTTPS；缺少这些变量时 Django 应在启动阶段 fail fast。
- 令牌有效期、登录限流、请求 ID 和审计日志应在部署环境变量中确认；不得把 `.env`、备份文件或密码提交到仓库。
- 数据库发布前执行 `deploy/postgres/backup-django.ps1`，恢复演练使用隔离目标和 `restore-verify-django.ps1 -ConfirmRestore`。
- `data_governance_report` 仅输出数据保留期候选统计；它不会清理历史数据，防止未审批任务误删审计或遥测记录。
