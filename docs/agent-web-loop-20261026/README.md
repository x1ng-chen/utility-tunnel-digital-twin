# 网页Agent闭环：实施与验收入口

2026-10-26，基于main f18d8bf的隔离工作分支。原工作目录、业务数据库、固件与V16/V17交付原件保留。当前软件已实现下列能力；实测结果单独见validation.json，不将自动契约检查当作模型全部事实正确。

## 已实现

- 四主控按左下1、右下2、右上3、左上4：31路11/7/6/7；P1→4、P2→3、P3/P5→1、P4→2，风机1→4、风机2→2。传感器编码和空间目标保持，清单带接线源文件SHA256与版本。V17模型主控文字仍为旧编号，界面明确提示。
- 单Agent继续使用现有DeepSeek工具调用。页面提供检测点、资产、工单的明确任务选择，避免靠“刚才那台”猜对象；先查快照、已有工单与手册后生成可确认草案，文字草案不算完成。权限由后端判断，只读角色的明确草案任务在调用模型前拒绝。
- 排障提供事实、候选解释、反证、缺口和下一项检查。覆盖零电压、缺测速、单测点异常及邻站不可用；A/mA归一化。旧控制审计不会当作新四主控动作，命令意图不等于转动，不给根因置信度或安全进入结论。
- 请求元数据记录布局、来源、实际模型标识、模型调用数、耗时和供应商Token用量。缺用量为未知，费用待账单核对；失败保留耗时与已有用量。证据编号必须存在；被拒绝工具只能证明调用失败/权限拒绝。模型自然语言没有被全面自动事实验证。
- 生产逻辑不接纳模拟数据为现场可用。独立验收环境只将显式simulation前缀计为场景可用；坏质量、未来、过期、离线依然不可用。现场数与模拟数分开显示。风机动画继续拒绝模拟rpm，不修改其现场行为门槛。

## 启动独立验收环境

在工程backend目录执行，使用已有安装好requirements.lock的Python环境：

```powershell
python manage.py migrate --settings=config.agent_eval_settings --noinput
python manage.py seed_agent_eval --settings=config.agent_eval_settings --case INS-01 --reset
python manage.py runserver 127.0.0.1:18926 --settings=config.agent_eval_settings --noreload
```

验收库固定为此隔离工程的`.agent-eval/db.sqlite3`，媒体、账号和记录均在`.agent-eval/`且已忽略。重置命令仅接受此专用数据库，普通/生产配置拒绝重置。`--reset`会清除该验收库的旧测试记录；不操作现有工程库。账号为agent-eval-operator/viewer/administrator，随机密码保存在本机`.agent-eval/users.json`，不要提交或放入视频。摄入服务账号无法读取助手；验收环境后端直接禁止硬件控制请求。

Vue在独立终端启动：

```powershell
$env:VITE_API_BASE_URL='http://127.0.0.1:18926/api'
npm run dev -- --host 127.0.0.1 --port 5186 --strictPort
```

先以运维员登录→打开助手确认“模拟测试”→五站巡检→选择P5排障→选择MQ4-05草案→审阅/取消或确认→按真实返回编号复核。创建后没有新采样时，应显示证据不足，不能自动结单。模型密钥仅由后端环境提供；浏览器和CI均不配置模型密钥。

## 场景与真实模型评测

`seed_agent_eval --case`支持INS-01～04、DIA-01～04、ORD-01～04，均可重置。模型使用实际V17 GLB，并经过原管理员上传、校验与启用门槛；没有伪造节点清单。缺绑定场景在合法启用后才清空测试资产的mesh。

```powershell
# 不带--live只列用例，不调用模型。
python manage.py evaluate_agent --settings=config.agent_eval_settings --suite smoke
# 以下明确触发付费模型；本地dotenv路径仅读取DeepSeek密钥，不回显或复制其他配置。
python manage.py evaluate_agent --settings=config.agent_eval_settings --suite composite --live --confirm-test-proposals --key-env-file 本机密钥文件路径
python manage.py evaluate_agent --settings=config.agent_eval_settings --suite regression --live --confirm-test-proposals --key-env-file 本机密钥文件路径
```

支持--case缩小至单题。--confirm-test-proposals仅模拟测试人员确认ORD-01/W04，并验证响应丢失后的同键重试；明确标识为测试程序确认，不冒充真人操作。普通模型不具有写工单工具。S05使用受控超时注入，明确不记作真实供应商超时。每条JSONL保留参考快照、原回复、证据/工具轨迹、模型用量、HTTP结果、确认结果、失败及待复核状态。自动调用/用例契约通过不代表自然语言事实全部通过；所有失败轮次保留。

## 对照与证据边界

```powershell
python manage.py export_agent_comparison --settings=config.agent_eval_settings .agent-eval中某轮记录.jsonl
python manage.py evaluate_agent_baseline --settings=config.agent_eval_settings 导出的comparison目录
# 仅增加--live才运行普通模型基线；密钥参数同上。
```

导出同一次冻结的原始证据和手册，移除Agent生成的候选解释及场景答案标签；M人工、L普通模型、A工具Agent共用来源。不得把预设故障原因提供给基线。自动导出耗时与人工准备时间分别统计；人工任务与双人事实评分需要参赛成员执行，CSV未测项保留NOT_RUN/空白，不填效率提升比例。

## 接口兼容与验证

保留POST /api/assistant/chat/、GET /api/assistant/inspection/与既有工单接口。新增只读GET /api/assistant/context/返回来源、布局与模型旧标签提示。chat可选task：draft+asset_code、diagnosis/inspection+station_id、review+work_order_code；严格校验字段与目标格式，客户端不能启用测试模式。原自由聊天仍可使用，明确任务会限制可调用工具并检查目标资产。响应新增runtime、diagnosis和integrity；inspection新增scenarioUsable，原usable语义不变。

自动测试包括生产与验收来源隔离、重置拒绝、映射、四类排障、无效引用、截断回复、草案完成性、权限、确认/取消及幂等。浏览器回归使用真实隔离API/工单/V17模型和明确标记的模型响应桩；真实DeepSeek效果另行记录，CI不调用付费服务。

历史的10月11日/24日方案与10月25日本地工作区检查仍是历史记录，不据其宣称当前数据库接入或真实硬件通过。本轮不部署公网，不接小智，不烧录设备。后续以最新身份映射核对真实遥测，再接同一业务Agent的语音和评委入口。

供应商工具调用与usage解析依据：[DeepSeek工具调用](https://api-docs.deepseek.com/guides/tool_calls/)、[Chat Completions接口](https://api-docs.deepseek.com/api/create-chat-completion/)，核对日期2026-10-26。没有引入新Agent框架或OpenAI SDK。

## 本轮实际验证（2026-10-26）

- 后端170项、前端116项通过（含真实V17 GLB）；生产构建通过。
- 新增3项无头Chromium浏览器回归全部通过，使用真实隔离API、模型和工单接口；模型文字响应为明确标记的桩，不冒充真实模型浏览器验收。
- 12个复合场景及30题回归的自动契约已完成。38题实际取得DeepSeek回复，3题由服务端权限拒绝且不调用模型，S05为受控超时注入。D03/A01采用等价查询工具的两题在修正规则后单独复测，原记录保留。
- 42题的逐句事实评分仍待团队复核，自动契约成绩不能写成“模型准确率100%”。M人工与L普通模型对照尚未执行；已导出12份冻结证据包、空白记录表并实现显式启动的普通模型基线命令。
- 共保留99条模型/权限/故障用例尝试记录，包含9条当时判为失败或阻塞的记录；其中既有软件问题也有评测器误判，不把该计数当模型错误率。早期截断试验与每轮原始输出保留，不只保留成功案例。汇总Token包括已知返回用量，费用仍需供应商账单核对。
- 本轮曾发现并修复验收账号未设置登录标识、场景绑定置空顺序、只读角色草案、文字冒充草案、回复截断与验收限流配置问题。日志位于本机artifacts/software-agent-20261025/publish与本隔离目录.agent-eval；未提交凭据、原始聊天日志或运行数据库。
