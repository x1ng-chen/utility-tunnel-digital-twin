# 审核与复现操作

## 安装及安全启动

保留现有业务库、演示库和旧评测库。新增迁移`0029_reviewed_experience`只创建经验表及其索引/约束，不回填历史经验，不批准旧记录。升级前先备份目标数据库，再以目标服务的settings执行`manage.py migrate --noinput`。PostgreSQL部署需由管理账号重新应用`deploy/postgres/provision.sql`，运行账号获得任务/经验的读写权限，但没有删除权限，也不能写模拟硬件动作表。

Windows本地现有包：

```powershell
python deploy/agent-demo/manage_demo.py stop
python deploy/agent-demo/manage_demo.py backup
python deploy/agent-demo/manage_demo.py start --no-paid-model
# 或 .\deploy\agent-demo\manage-demo.ps1 -Action start -NoPaidModel
```

启动器会执行迁移。`--no-paid-model`覆盖**本次进程**中的DeepSeek密钥，不改写私有`.agent-demo/.env`，也不移除三维模型。普通启动仍使用既有配置；没有显式获准真实模型复测前，不用网页任务按钮运行付费任务。

服务端可设`AGENT_EXPERIENCE_ENABLED=false`停止新任务检索经验；列表及审核记录保留，已冻结任务不被改写。客户端不能指定经验ID、伪造审批、切换来源或开启测试模式。停用时不要回退迁移来删除历史表。

## 从候选到共享

1. 新三Agent任务必须经历复核要求修改、诊断内容实际改变、再次复核通过，且任务契约通过。仅白名单结构化问题生成候选，无法可靠抽取时不生成。
2. 所有者在工作台“受控复核经验”查看自己的候选；管理员查看脱敏队列。无原始提示词/整段回复/私有轨迹分享入口。
3. 管理员核对设备、工位、指标、来源、布局/规则/知识版本及提醒内容，选择批准或驳回。提醒不应包含个人信息、地址、凭据或执行指令。词法过滤只能拦一部分问题。
4. 批准后仅管理员和运维员匹配加载，最多3条；模拟、数据库观测等来源分别匹配。查看者不加载共享提醒。
5. 修改使用“修订为新候选”，原条目不变。批准最新修订会退役原批准版本；过时分支、重复审批和旧revision返回冲突，刷新后重新核查。已批准条目可以退役，退役后不再注入新任务。

状态：候选→已批准/已驳回；已批准→已退役。修订产生新候选，不把原条目改回候选。审批审计是管理员操作记录，不是独立现场事实认证。自动化测试使用专门的模拟审批标记。

## 接口

- `GET /api/assistant/experiences/?status=candidate`：所有者私有候选/管理员脱敏队列；运维员另可见已批准提醒。超过100条明确标记截断。
- `GET /api/assistant/experiences/{uuid}/`：按同一可见性校验；别人私有条目返回404。
- `POST /api/assistant/experiences/{uuid}/`：`{"action":"approve|reject|retire","revision":1}`；只有管理员可操作。修订为`{"action":"revise","revision":2,"lesson":"脱敏提醒"}`，由所有者运维员或管理员提交。
- 未授权403、不可见404、版本/并发/重复内容冲突409、非法字段400。审批不接受客户端提供的状态、所有者、来源或审核记录。
- 原任务接口增加只读`guardrails`和`experienceContext`。导出仍为JSON/CSV/可打印HTML；完整上下文与版本冻结在JSON证据包中。

## 离线复现

安装原有锁定依赖后，在`backend`执行；这些命令不访问模型供应商：

```powershell
python manage.py makemigrations --check --dry-run
python manage.py test operations.test_guardrails operations.test_reviewed_experience operations.test_software_sprint
python manage.py migrate --noinput --settings=config.guard_eval_settings
python manage.py evaluate_guardrails --settings=config.guard_eval_settings
python manage.py evaluate_guardrails --settings=config.guard_eval_settings --offline --experience paired --with-experience-fixture
```

默认只列目录；必须显式`--offline`才执行桩。结果保存在独立`.agent-eval-guards/runs/{time-id}`，不重置演示/业务/旧评测数据，后续运行也保留以前记录。`benchmark.lock`防止同时运行。中断后先确认进程已结束再处理锁，不直接重置库。

训练夹具独立编写：90mA与缺质量零RPM，不引用J矩阵的结构化答案。评测只加载本次指定训练来源，排除同库旧夹具经验；各臂冻结来源一致。模拟管理员批准仅用于测试，不标为真人。普通CI会运行此矩阵且密钥为空。

原有12/30题默认目录检查：

```powershell
python manage.py evaluate_sprint --settings=config.sprint_eval_settings --suite composite --mode paired
python manage.py evaluate_agent --settings=config.guard_eval_settings --suite regression
```

这两条是目录检查，不是假装完成历史回复重放或真实模型评测。`--live`接口为后续显式授权付费复测准备，本轮不执行。真实Token、账单费用、事实评分和编排/经验收益保持未知。

导出本轮明确的离线记录，在工程根目录执行：

```powershell
python deploy/agent-demo/export_guardrails_evidence.py --run <runs下的目录名>
```

导出器校验100行、四臂观测一致、训练与留出独立及全部契约通过；只打包已知离线JSON/JSONL与清单，检查本地凭据精确匹配，排除数据库、账号文件、密钥、权重和生产数据。ZIP内有逐文件SHA256，外部摘要另有ZIP散列。

## 页面回归的边界

`tools/e2e/agent.spec.cjs`新增两项：护栏/原始证据/解释分层、旧任务、审批revision、新候选、退役；查看者无审核入口。页面响应使用明确的夹具。真实权限、事务、去重、隐私和版本冲突由Django测试验证，不将浏览器程序点击算真人审批。

原V16/V17不改写，旧主控文字标签仍按既有说明提示；本轮不宣称完成模型身份迁移。实物、语音和公网仍是后续工作。
