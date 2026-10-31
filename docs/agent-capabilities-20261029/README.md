# 可续查运维 Agent 与本地只读决策（2026-10-29）

本轮在独立工作区实现软件能力，保留 Django／Vue／DeepSeek 三 Agent、原有权限、设备证据护栏和受控复核经验库。原工作区未改动；同步了远端 main 的 V24 模型交付文件，没有切换现用 V20 呈现或修改实物固件。

K210、照片／视频理解、视频转技能、真实控制和付费 DeepSeek 复测继续暂缓。本页区分代码功能、桩回归、本地小模型实测和仍未完成的验收。

## 已实现的六项能力

| 能力 | 实际行为与边界 |
| --- | --- |
| 设备依赖拓扑 | 冻结31路、四控制器、五站、网关、485及双风机配置，按目标查询依赖与影响。共用主控支持排查候选，不证明根因。期望模型映射与已核验绑定分开；不根据3D坐标猜电气连接。 |
| 可续查排障 | 保存候选解释、支持／反证、缺项、待办检查和每轮快照。人工填写“已检查／无法检查”后建立新任务，保留旧判断。人工报告不是仪表测量，不自动恢复告警或关闭工单。 |
| 本地 AnyJev 路由 | Tacit-1.7B 在闭集选项中选择只读检查，由服务器执行并记录真实 E 轨迹。无效、缺证、低间距或超时可回退；默认关闭。不是只展示路由动画，也不允许小模型生成任意工具或参数。 |
| 独立分支推演 | 从同一冻结模拟快照比较至多三种双风机方案。独立计算，不更改演示采样、业务库或硬件。回执／输出／RPM分开；不预测气体扩散，不用回执解除告警。 |
| 受审只读流程 | 可从自己的已完成任务提取成功只读工具步骤，或手动编写候选。管理员审核前进行零模型、零命令的工具可执行性回归。候选不生效，获批后按来源和版本匹配并冻结内容散列；退役后不再加载。自由文本条件仍需复核。 |
| 失败轨迹分析 | 定位已记录的首个契约问题、护栏违规、被拒工具、结构修正及缺失产品，生成待审回归候选。不自动改规则、不训练模型、不发布知识；没有已记录问题不代表诊断正确。 |

身份保持11／7／6／7归属，FAN-01属于CTRL-04，FAN-02属于CTRL-02；P5没有温湿度。系统仅两台排风机，没有水泵。未经标定的MQ／氧气ADC不能升级为可信浓度或安全进入结论。

## 使用流程

在 Agent 工作台选择明确检测站，创建排障档案并开始诊断。展开任务证据，可查看原始观测、配置关系、本地决策分布、真实执行检查和回退原因。诊断产生人工待办后填写检查报告，再点“继续排障”；新旧快照和候选历史保留。

完成任务后，可显式生成“分支比较”或“失败轨迹分析”。流程复用通过“从本任务提取流程候选”进行，管理员看到候选后审核；只有匹配布局、模型、知识、规则及数据来源的已批准版本才能执行。模拟流程不能直接用于现场判断。档案和原任务始终按所有者隔离；共享的是经过批准的流程内容，不开放其他人的任务接口。

本轮模拟分支使用显式教学参数：60秒、PWM50%、1200rpm、3.6W，均非实测风机曲线。没有实际电价，不给电费；没有已批准的场景通风约束，不进行节能合规排名。实际快照与教学初态冲突时报告缺口，不覆盖观测。

## 验证结果与尚未证明的内容

| 验证层 | 本轮实际结果 | 不代表什么 |
| --- | --- | --- |
| Django完整回归 | 365项通过，迁移无漂移、系统检查通过 | 不代表31路实物、付费模型或浏览器视觉验收 |
| Vue回归／构建 | 164项通过、1项既有跳过；TypeScript和Vite构建通过 | 新界面尚未在可控浏览器中视觉走查；原运行页面未重启 |
| 本地服务HTTP契约 | 7项通过，显式桩引擎 | 没有用桩伪装模型推理 |
| 初轮本地模型12例，策略v1 | 10例符合开发者预设可接受检查；5次选择、7次回退 | 两例未命中是选择“不确定”，不是都因分布接近 |
| 留出本地模型16例，策略v2 | 12例符合预设检查；8次选择、8次回退；16例路由契约通过 | 开发者编写的小样本，未进行独立人工评分，不是故障诊断正确率 |
| 三组联合编排 | 每组12次请求：11次完成所需工具契约、1次查看者工单403拒绝；生成式Agent全部为显式桩 | 不能比较三Agent真实语义质量或宣传编排收益 |
| 联合流程实际小模型路由 | 13次请求中2次选中并执行检查，10次“不确定”回退、1次低间距回退 | 目前没有证据证明提高排障效率；保持实验选项 |
| DeepSeek真实三Agent／独立评分 | 暂缓，未新增付费调用 | 不填写提升率、诊断准确率和经济收益 |
| GitHub CI／Docker GPU | 已补离线CI配置；本轮未执行远端CI或容器GPU运行 | 本地通过不等于远端部署通过 |

留出16例端到端路由中位86ms、最大547ms；联合流程测得显存最大已分配3482.78MiB、保留3562MiB。不同输入和设备会变化；这些不是整套Agent耗时或全机内存峰值。

保留初轮工单桩使用无效优先级的失败记录，修正桩后重跑；没有通过修改业务校验掩盖失败。失败、回退与版本修订均进入证据归档。

## 复现：不触发付费模型

普通回归使用正常测试设置，别用刻意禁止现场控制的验收设置替代整个后端测试配置：

```powershell
$python = 'D:\shixi\utility-tunnel-digital-twin\artifacts\publish-agent-qa-20261025\Scripts\python.exe'
$env:DJANGO_SETTINGS_MODULE = 'config.settings'
$env:DJANGO_ENV = 'test'
$env:DATABASE_URL = ''
$env:DEEPSEEK_API_KEY = ''
$env:ANYJEV_ENABLED = 'false'
& $python backend/manage.py test operations --noinput
& $python -m unittest discover -s services/decision-router -p 'test_*.py'
cd frontend
npm test -- --run
npm run build
cd ..
```

三组矩阵只允许独立 `.agent-capabilities` 库，必须显式 `--reset`。这会重置该库内的演示用户、任务和档案；先备份自己的新演示记录。业务、`.hardware-live`、`.agent-demo`和旧评测库不受影响。

```powershell
& $python backend/manage.py migrate --settings=config.agent_capability_settings --noinput
& $python backend/manage.py evaluate_agent_capabilities --settings=config.agent_capability_settings
# 无执行参数时只列用例。下面是显式决策桩；生成式Agent也始终为桩
& $python backend/manage.py evaluate_agent_capabilities --settings=config.agent_capability_settings --offline --reset
# 先按本地服务说明启动。仅决策器为真实本地模型，生成式Agent仍是桩
& $python backend/manage.py evaluate_agent_capabilities --settings=config.agent_capability_settings --local-model --reset
```

[本地模型安装、启停与配置](../../deploy/decision-router/README.md)。普通测试和CI不下载权重、不调用本地GPU、不调用付费模型。

## 独立网页演示

为避免覆盖现有实物联调服务，使用新库和不同端口。下列命令不自动设置模型密钥；不配置DeepSeek时可查询、管理档案和候选，真实三Agent任务会报告缺少配置，不生成假回复。

```powershell
$env:DJANGO_SETTINGS_MODULE = 'config.agent_capability_settings'
$env:DJANGO_ENV = 'development'
$env:DEEPSEEK_API_KEY = ''
& $python backend/manage.py migrate --noinput
& $python backend/manage.py run_agent_demo --initialize --without-model --once
& $python backend/manage.py runserver 127.0.0.1:18927 --noreload
# 第二个相同环境的终端：
& $python backend/manage.py run_agent_demo
# 第三个相同环境的终端：
& $python backend/manage.py run_agent_worker
# 第四个终端，在仓库根目录：
$env:VITE_API_BASE_URL = 'http://127.0.0.1:18927/api'
cd frontend
npm run dev -- --host 127.0.0.1 --port 5187 --strictPort
```

访问 <http://127.0.0.1:5187/agent-workbench>，账号凭据保存在本工作区 `.agent-capabilities/users.json`，不要公开。使用真实API登录，管理员启动采样。`--without-model`避免依赖旧V17的LFS文件；未安装模型绑定时明确显示缺口。暂停停止新样本／心跳，恢复产生新时间观测；界面重置更换场景代际并保留旧任务快照，旧档案不冒充新场景。

需要真实模型任务时由用户单独配置DeepSeek和明确启动；本轮没有进行这一步。不要在已运行的实物联调进程中改设置，也不要并行占用已有5187／18927端口。原Docker软件包可继续使用，默认禁用本地路由；跨容器连接另行适配。

## 新接口

所有接口位于 `/api/assistant/`，使用既有鉴权；客户端不能提交来源、版本、工具参数扩权或测试模式。

| 方法与路径 | 用途 |
| --- | --- |
| GET／POST `cases/` | 只列本人的排障档案／创建 |
| GET `cases/{id}/` | 快照、候选与待办历史 |
| POST `cases/{id}/feedback/` | 检查编号、报告、状态、revision；冲突409 |
| POST `runs/` | 兼容旧接口，新增可选case_id／procedure_id；重复请求幂等 |
| GET `topology/?target=...&relation=dependencies` | 已配置设备关系 |
| POST `branches/` | 基于本人的已完成任务，只读生成分支比较 |
| GET／POST `procedures/` | 自有候选／已批准流程，或管理员审核队列 |
| POST `procedures/from-run/` | 显式提取本人的成功只读步骤为候选 |
| POST `procedures/{id}/review/` | 管理员approve／reject／retire，版本冲突409 |
| GET `runs/{id}/analysis/` | 本人的已记录失败轨迹及待审回归建议 |

数据库迁移0031只新增三张表及AgentRun可空外键。PostgreSQL应用角色补齐对应表权限，分支比较记录仅允许追加／读取。任务保存拓扑／呈现版本、候选、审批内容散列、执行轨迹、模型、耗时和可用用量。

## 证据文件与下一步

- [结构化结果](validation-summary.json)：最终回归数量、模型路由结果、记录散列。
- [初轮12例](local-router-evaluation.json)、[留出16例](local-router-holdout-v2.json)：输入、闭集选项、真实分布、未命中和时间。
- `evaluation-records.zip`：初轮失败、修正前后联合矩阵，包含冻结模拟快照和真实本地轨迹；不含私有账户、服务令牌或环境文件。
- [归档校验清单](evidence-manifest.json)：各记录SHA256与文件大小。

下一步应在额度和可控浏览器恢复后，分别做真实三Agent同数据配对评测及新界面视觉走查；使用人工评分判断诊断与引用质量。当前不预设多Agent或本地决策器优于原流程。小模型未命中应先分类分析，不能把回退率或契约通过率写成事故拦截率。
