# 软件演示收尾：第一阶段交付

2026-10-29。统一新Agent工作台和V24，完成版本阻塞修复及本机演示验收；真实DeepSeek小批量复测已显式启动，但首个请求收到HTTP402，批次停止。本轮不是完整参赛验收通过。

## 当前可用

访问 <http://127.0.0.1:5187/agent-workbench>。这是独立模拟软件环境；实物联调仍使用8000／5173端口，两者数据库和控制权限分离。

- 演示和评测默认安装精确V24，31路采集身份与11／7／6／7归属保持；场景重置恢复当前V24映射，不回填旧V17网格。
- 已存在的演示库可幂等升级，保留用户、任务、档案和原快照；缺失或错误GLB在任何清库操作前拒绝。
- 经验批准统一核对布局、呈现版本、模型SHA、规则、知识、数据来源和原始证据。V24候选可审核，跨版本或未知模型不冒充兼容，退役后不再注入。
- 工作台突出巡检五站、排查异常、准备工单、恢复复核；场景管理和高级工具默认收起。点击入口仅准备表单，不自动请求模型、执行控制或创建工单。
- 启动器默认关闭DeepSeek传输和AnyJev；服务端直接提交任务也返回503且零新增，不能仅通过前端按钮限制绕过。
- 启停核对进程身份；备份包含已提交WAL，恢复前保留当前状态并校验profile，拒绝跨库和越界归档。

## 启动和凭据

在本工作区根目录，使用已有Python环境，无须改动它的依赖：

```powershell
$python = 'D:\shixi\utility-tunnel-digital-twin\artifacts\publish-agent-qa-20261025\Scripts\python.exe'
./deploy/agent-demo/manage-demo.ps1 start -PythonPath $python
# 停止、备份、恢复均只针对本profile
./deploy/agent-demo/manage-demo.ps1 stop
./deploy/agent-demo/manage-demo.ps1 backup
```

Node.js需在PATH中。当前已启动，重复start会拒绝。管理员账号为 `agent-eval-administrator`，运维员为 `agent-eval-operator`；密码只在本机 `.agent-capabilities/users.json`，未写入本报告、截图或公开附件。原实物页面账号未更改。

[完整启动／备份恢复说明](../../deploy/agent-demo/README.md)。`--profile demo`保留旧软件目录；capabilities不接受其备份。Docker包补入V24并排除私有运行目录，本轮只检查打包规则，没有运行容器。

## 验证分层

| 验证 | 实际结果 | 边界 |
| --- | --- | --- |
| 后端完整回归 | 398项通过 | 普通测试无付费请求，模型使用显式桩 |
| 前端回归 | 179项通过，实际V24GLB参与，无跳过 | 不能代替真实诊断质量 |
| TypeScript／生产构建 | 通过 | 当前运行的是本机演示 |
| 启动器专项 | 16项通过 | 包括进程身份、默认禁止付费、WAL、跨profile和路径拒绝 |
| 本机实际服务 | V24就绪、37个业务资产映射、31路唯一目标；启停与备份恢复通过 | 所有采样为模拟，没有硬件控制 |
| 历史保留 | 升级前任务快照／结果及档案仍在 | 历史版本未倒填为V24新结果 |
| 页面走查 | 实际登录、任务入口、禁用提示、创建档案成功；窄屏375px内容未横向溢出 | 未完成真实模型运行／所有弹窗与权限的全量页面验收 |
| 检索运行方式 | keyword_fallback，明确降级 | 当前环境未验证BGE混合检索；不把命中当作条款语义正确 |
| 真实DeepSeek | INS-01一次请求HTTP402；DIA-01、ORD-01未运行 | 未取得模型答案／Token用量，不产生通过率或提效结论 |
| 远端CI／main | 本轮未执行远端CI，尚未作为完整验收版合并 | 本地回归不等于GitHub检查通过 |

[接口实际验收](runtime-acceptance.json) · [真实模型批次状态](live-smoke-status.json)。桌面／窄屏截图均来自实际服务，未注入假页面响应。

## 恢复真实复测

当前使用的已保存DeepSeek配置仍收到余额不足。不要自动循环重试或换成桩继续填成绩。额度恢复后，使用独立发布评测配置：

```powershell
& $python backend/manage.py migrate --settings=config.software_release_eval_settings --noinput
& $python backend/manage.py evaluate_sprint --settings=config.software_release_eval_settings --suite smoke --mode multi --live --key-env-file 'D:\私有目录\模型配置.env'
```

该配置将本轮记录放在 `.agent-eval-sprint/release-20261029/.agent-eval-sprint/runs`，保留此前402记录；每次新批次另存文件。AnyJev保持关闭。普通命令不加`--live`只列用例，网页启动不加显式允许参数也不会读取付费凭据。

本轮模型输入为V24冻结模拟证据。每任务仍为120秒、12次模型与12次工具上限；401／402／403立即终止后续批次。服务商未返回实际模型和Token时保持未知，费用以账单核对。

真实模型通过三个主流程后，再验证人工反馈后续查、新证据修正、工单确认与恢复复核、流程提取审批及经验批准／退役。随后才扩大到12复合配对、30题及护栏／知识集合，并安排独立人工评分。当前没有生成、批准或展示任何伪造的“学习成功”经验。

## 后续仍待完成

1. 补足当前DeepSeek账号额度，重跑三条主流程并修复真实回复问题。
2. 完成模型运行中的页面走查、权限／取消／超时和档案续查全流程。
3. 完成同数据配对评测与独立评分，再统一发布GitHub、合并main和冻结演示版本。

实物、语音、公网及K210继续暂缓。当前没有新增预测、MCP或自动结单。

![实际工作台](workbench-overview.jpg)
