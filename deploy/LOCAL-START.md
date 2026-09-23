# Windows 本地启动

先按项目 README 安装 Node.js、后端虚拟环境与前端依赖，并完成经确认的数据库初始化。脚本不会安装依赖、迁移或填充演示数据。

从仓库根目录运行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File deploy/start-local.ps1
```

这里的执行策略参数只作用于新进程，不更改系统全局策略。仅运行自己已审查的仓库脚本。

只检查依赖、端口与服务就绪状态：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File deploy/start-local.ps1 -CheckOnly
```

- 前端：http://127.0.0.1:5173/；后端：http://127.0.0.1:8000/api。
- 脚本用 `daphne -b 127.0.0.1 -p 8000 config.asgi:application` 启动 API，同一 ASGI 进程提供 HTTP 与 WebSocket；请安装当前锁定依赖。脚本会复用旧的健康服务，不会主动将运行中的旧 WSGI 进程替换为 ASGI；更新后需确认原进程归属再人工重启。HTTP 就绪本身不证明 WebSocket 已连接。
- 已就绪服务直接复用，不重复启动；端口被其他服务占用或 API 未就绪时明确失败，不杀进程、不换端口。
- 新服务在后台启动，日志放在 `.runtime/`（已忽略，不提交）；启动进程编号显示在终端中。
- 缺少迁移时停止并提示，须人工确认数据库后执行迁移。不会重置账号、密码或数据。
- 若浏览器仍指向旧 `vue-api-url`，脚本不能修改浏览器存储；按使用手册检查服务地址。
- 本脚本只用于本机开发/演示，不是生产部署器，不向局域网公开开发服务。

当前验证：已有服务时只读检查和幂等启动通过；production 环境拒绝、实际非 development 配置拒绝均通过。无服务冷启动、端口冲突、依赖缺失、数据库失败等分支还需隔离测试，不能视为全部验收。
