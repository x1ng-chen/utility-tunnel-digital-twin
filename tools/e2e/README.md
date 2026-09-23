# 浏览器回归

## 本地安全运行

业务用例会创建账号、资产、工单与模型版本。不要直接对演示或生产数据库运行。

1. 保持前端在 `http://127.0.0.1:5173` 运行。
2. 使用项目的 Python 环境启动 `tools/e2e/isolated_api.py`。它在系统临时目录中创建全新的 SQLite 数据库和模型上传目录，仅监听本机 `18000` 端口，不修改 `backend/db.sqlite3` 或 `.env`。
3. 为测试进程设置 `E2E_API_URL=http://127.0.0.1:18000/api`。测试会话通过初始化脚本选择该 API，不改变开发前端配置，也不影响其他浏览器会话。
4. 使用已安装的 `@playwright/test` 运行 `ops.spec.cjs`，配置文件为 `tools/e2e/playwright.config.cjs`。
5. 完整重跑前，先停止独立 API，再重新启动，确保没有上一轮留下的唯一节点或模型版本。不要通过删除唯一性校验让测试通过。

端口被占用时启动器会在创建测试数据前退出，不会自动复用旧服务。可以传入 `--port 18107`，并把测试进程的 `E2E_API_URL` 同步设置为 `http://127.0.0.1:18107/api`。以本次启动输出的端口为准，不能仅看到“已生成种子数据”就认为服务已成功绑定默认端口。

PowerShell 示例（在仓库根目录；`NODE_PATH` 应指向你实际安装测试依赖的目录）：

```powershell
backend/.venv/Scripts/python.exe tools/e2e/isolated_api.py
```

另一个终端：

```powershell
$env:E2E_API_URL = 'http://127.0.0.1:18000/api'
node "$env:NODE_PATH/@playwright/test/cli.js" test --config tools/e2e/playwright.config.cjs ops.spec.cjs --reporter=line
```

Windows 下包含 `|` 的 `--grep` 参数应直接传给 Node CLI，避免 `.cmd` 再次解析它为管道。

若本机无法下载 Playwright 托管浏览器，可仅为该隔离测试会话设置 `E2E_CHROMIUM_PATH` 指向已审查的 Chrome/Chromium 可执行文件；该变量不会写入项目配置，也不会改变 CI 的托管浏览器。不要将此回退用于生产浏览器兼容性结论。

停止独立 API 时会关闭数据库连接并清理临时目录。异常强制结束进程可能留下临时目录；只清理启动日志中明确列出的 `ut-e2e-isolated-*` 目录，不删除演示数据。

## 检查范围

- `ops.spec.cjs`：登录、滚轮不跳页、三维模型与相机交互、跨页面定位、全屏指针、审计、三秒操作提示、告警转工单、权限、注册审批、资产/GIS 版本维护与模型发布；另在已打开告警页且实时连接成功后，验证遥测越限产生的新告警在 3 秒内通过 WebSocket 显示，并在三维页验证同一实时告警在 3 秒内自动聚焦至已绑定设备节点。
- `visual.spec.cjs`：11 个页面的桌面布局，以及 1366、1600、1920 三档分辨率；检查收起侧栏的图标居中与低高度滚动。另覆盖 390、768 两档窄屏的整页溢出、底部导航、退出入口及手机首页设备按钮互不遮挡。它不证明所有样式美观、所有触摸手势或完整业务正确。
- 失败截图、调用上下文和 trace 位于 `tools/e2e/test-results`；视觉巡检截图位于 `test-results/visual-audit`。
- 窄屏巡检截图位于 `output/playwright/mobile-audit`，仍需人工检查文字密度、遮挡和交互意义。巡检会先等待侧栏成为固定底栏后再测量，避免 Vite 初始样式注入的单帧状态造成误报；若未在断言时限内固定，仍按真实布局失败处理。

基础安全扫描、类型检查和单元测试不能替代浏览器回归；单次回归通过也不代表完成全部交付审查。
