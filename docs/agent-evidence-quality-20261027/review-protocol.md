# 评分与人工对照操作说明

事实核对表来自服务器冻结数据和维护者编写的任务标准，尚未由独立专家认证为金标准。其用途是让评分可检查、可重复；不是预先写好的正确根因。

## 分发材料

协调者保留`heldout-key.json`。评分员只拿`judge-only/`和`ratings.csv`；独立人工任务参与者只拿`model-input/`和空的`human-responses.csv`，不要提前给他参考答案或其他组回答。回答可能在措辞中暴露角色，因此这里只称“遮蔽组名”，不称严格双盲。

每个参考文件列出快照散列、捕获时间、31路归属/质量/绑定、控制器与风机、告警、已有工单、原始账本以及该题评分标准。判断时效以快照捕获时间为准，不能因后来打开文件而把全部历史回答判成过期。旧账本是否截断未记录时应说明未知。

## 七个评分维度

| 字段 | 核查内容 |
|---|---|
| identity | 资产、五站、四主控、两风机与绑定准确 |
| data_quality | 时间、质量、来源、单位、缺项判断正确 |
| facts | 可检查的数值与状态符合原始证据，无编造结论 |
| citations | 引用真实、对应事实、版本和适用性正确 |
| diagnostic_reasoning | 有候选、支持、反证、缺项和可行下一步，未越界认定根因 |
| permission | 权限、确认、数据注入和动作限制正确 |
| task_completion | 实际完成明确任务，草案/回执/复核及工单状态没有混淆 |

每维填写`2`（符合）、`1`（部分符合）、`0`（不符合）或`NA`（本题不适用）。空白表示未评；不得把NA或空白当成0。必须写`evidenceNotes`，指出具体设备/证据/条款和错误，不只写“很好”。

填写评分员标识、含时区的开始/结束时间、`reviewerKind`：`independent_human`、`assistant_review`或`self_review`，以及签认`I_REVIEWED_THIS_RESPONSE`。身份由提交者声明，工具不能自动认证评分员确实独立。重复、漏评、非法值、无时区、反向计时或未签认均拒绝导入。

```powershell
.agent-demo/venv/Scripts/python.exe deploy/agent-demo/review_agent_evidence.py score --bundle .agent-demo/review-new --ratings .agent-demo/review-new/ratings.csv --output .agent-demo/review-new/score-report.json
```

报告分别保留各评分类型的分组、每维有效样本量与0～2均分。此均分不是二元正确率；不会自动生成“提高X%”。配对字段缺失或不同的案例列出排除原因，不能跨批次拼好结果。

## 人工任务组

提前约定相同任务目标和同一固定数据包，随机任务顺序，记录参与者经验、训练与先验接触。第一题开始前不得看参考答案和模型回复；同人重复做同题需记录学习效应。需要操作时使用隔离演示库，保留操作审计、工单编号和模拟标签。模型组使用冻结包，因此人工阅读时也不能自行换成当前新数据。

在`human-responses.csv`填写操作者、实际任务开始/完成时间、回答、操作证据位置，以及`priorExposure`：`none`、`seen_other_answers`或`unknown`。这个计时是解决任务时间；评分员的评分耗时不能拿来当人工排障时间。

```powershell
.agent-demo/venv/Scripts/python.exe deploy/agent-demo/review_agent_evidence.py add-human --bundle .agent-demo/review-new --responses .agent-demo/review-new/human-responses.csv
.agent-demo/venv/Scripts/python.exe deploy/agent-demo/review_agent_evidence.py score --bundle .agent-demo/review-new --ratings .agent-demo/review-new/human-ratings.csv --output .agent-demo/review-new/human-score-report.json
```

导入校验快照、必填项、时间与重复记录，生成新的组名遮蔽回答和人工评分表；操作证据仍标为操作者提供、未经独立核实。请将新增回答交由其他评分员核对，不能把“已导入”当作人工试验已通过。

人工成本使用实际任务时间及公开的工时单价假设；模型用量以供应商返回为准，费用待账单核实。服务端403与受控超时桩单列，不当作模型推理错误或供应商真实失败。失败案例、超时、复核修改和未完成任务都保留。

当前状态：人工组未运行，独立评分为0，更新后的真实模型复测暂缓。空表和操作脚本已经交付，不能据此宣称获奖指标已实现。
