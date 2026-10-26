# 本地网页演示操作

先按README启动独立验收环境，再访问前端。当前开发端口为http://127.0.0.1:5186，API为http://127.0.0.1:18926/api；只有本机可访问，不是评委公网入口。

账号：agent-eval-operator。随机密码在工程根目录`.agent-eval/users.json`的operator字段；不要放进视频或提交GitHub。

## 先刷新场景

在backend目录执行：

```powershell
python manage.py seed_agent_eval --settings=config.agent_eval_settings --case INS-01 --reset
```

这是静态种子，不是持续硬件遥测。默认约3分钟后心跳/样本会如实过期；每轮演示前重置，仅清除独立验收库中的旧测试工单等记录。不要把过期状态伪装成实时在线。模型密钥需已配置在后端进程环境。

## 三条网页流程

1. **五站巡检与定位**：登录，打开AI助手，确认“模拟测试”标识，点“五站31路巡检”。新种子应为31路登记、模拟场景可用31/31、现场可用0/31。展开设备入口，分别定位五站和P5的MQ4-05、CO-05；V17旧主控文字提示应保留。
2. **P5排障**：检测点选P5，点“排查检测点”。核对引用、当前值与趋势、双风机、控制审计、候选原因、反证和缺口。不能把模拟请求说成实际动作，不能将ADC当ppm。需要展示供电异常、无测速、单探头变化、邻站过期时，用DIA-01～04分别重置后重复。
3. **工单与恢复复核**：设备选MQ4-05，点“生成处置草案”。先取消，确认没有新增；再审阅并确认，记录真实返回的WO编号，点“复核这张工单”。当前新采样不等于测量恢复，当前online不等于已证明恢复过程；不会自动结单。

只读验证可换agent-eval-viewer：允许查询，不能生成/创建工单。隔离环境禁止硬件控制；演示不需要连接或启动实体风机。

## 自动网页复现

普通浏览器回归的模型响应为桩；真实模型网页测试另设显式付费开关。先刷新INS-01，前后端保持运行。以下命令在工程根目录执行；首次安装测试依赖和Chromium，以后可复用：

```powershell
npm install --prefix .agent-eval/browser-tests --no-save @playwright/test@1.55.0
$env:NODE_PATH=(Resolve-Path .agent-eval/browser-tests/node_modules).Path
node .agent-eval/browser-tests/node_modules/playwright/cli.js install chromium
$env:E2E_WEB_URL='http://127.0.0.1:5186'
$env:E2E_API_URL='http://127.0.0.1:18926/api'
$env:AGENT_E2E='1'
$env:AGENT_LIVE_E2E='1'
node .agent-eval/browser-tests/node_modules/@playwright/test/cli.js test --config tools/e2e/playwright.config.cjs agent.spec.cjs --grep '真实模型网页闭环'
```

该用例用程序在网页执行确认，不冒充真人确认。记录实际回复、请求编号、供应商模型和Token，写入本地`.agent-eval/browser-live-*.json`；事实评分仍待复核。普通测试和CI不设置AGENT_LIVE_E2E，不调用该付费用例。测试后工单留在隔离库，可在下一轮演示前重置。
