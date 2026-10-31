# 语音联调断点 2026-10-29

当前发布补充：停止词已覆盖Speaking及Listening，两种场景实物复测通过；AI_ASSISTANT_RATE_LIMIT=none关闭应用查询次数限制，鉴权保留。最新固件及SHA以firmware/xiaozhi/stop-states-build-report.json为准；下面旧应用SHA与历史测试为此前阶段快照。

最新修正：用户反馈每轮加“还未核查现场数据”。根因是client.py的场景分类和fallback统一前缀，不是DeepSeek每轮都生成。现已删除整套分类器和_spoken_reply，问答格式/角色/proposals校验后直接返回reply.strip()，mode/queried_at元数据原样保留，不再自动补任何开场。不要恢复基于关键词的免责声明词表，也不要全局删除模型回答中的具体限制。

VOICE_STYLE只对语音页面禁固定开场，真正没数据就具体说“P1没有新采样，暂时无法判断”，未知/过期/校准限制和工具权限保留。124项语音回归及5项后端语音路由检查通过；测试数量变化是移除旧分类器专用断言并改成内容保真/无前缀回归。真实DeepSeek聊天、知识解释和P1查询均不带统一开场；详情server/no-prefix-test-report.json。只改服务器，无需重新烧录，音量80与固件不变。

发布前最近一次联调中，Django、语音网关和Breeze健康检查均为HTTP200，适配器来源/部署哈希一致。进程ID与局域网地址随机器和重启变化，恢复时由启动脚本及串口重新发现。下面保留本轮其他功能和历史验证信息。

当前已完成：DeepSeek真实接入（沿用backend/.env现有Key）、一般知识和多轮追问；用户确认连续回答正常、音量80清楚。两轮数学API测试得到8→10，知识问题能衔接主题；不是固定答案。普通身份/问候/测试不再强制读长开场；现场未查证或未知数据限制仍保留。一般知识不需要先查现场数据，但P站/当前状态/执行结果不能按闲聊省略核查。

本轮源文件：backend/operations/ai_assistant.py的VOICE_STYLE；voice client.py、utility_tunnel.py，新speech_input.py及测试。输入正规化仅复制最新user内容，原始ASR历史保留；P一/P 1/一号检测点→P1，明确MQ二零一→MQ2-01；未知P10/十一号站/AP1/未知MQ型号和气体名称不乱改，不会把“点现在什么状态”猜成P1。现场音频P1对照测试未完成，第一轮用户明确说未按步骤问P1；不能把当时背景转录计作P1漏检。合成SAPI+Paraformer三个明确ID通过。

固件当前应用SHA256 17dfe13db3c9f68e557e1b06948efdd059f2bfff4b09a34c8b64cb86548c8231，2406336字节。
assets SHA256 80d109b00f376d695ee0c076336e7feeeb47fa9ea35a11f10665d0c01b337257，2951624字节，未变。
本次只写app0x20000并校验bootloader/partition/app/assets四静态镜像。Wi-Fi、设备凭据、运行时otadata保留；audio音量NVS按请求改80。唤醒词“你好，小管/小管”，回应“我在呀，你说！”；停止词“不用说了/闭嘴”，本地回复“好的，需要时请随时叫我”后Idle。

网络ACK tail从300ms改150ms；AudioInputTask仅在专用联网板且输入已开启时跳过120ms重复延迟，cold及其他板不变。热路径显式等待减少270ms，不能据此声称声学准确率提高多少。原40音量/旧采音回滚分别在D:/ut-voice/rollback/voice-quality-volume40-before80-20261029与listen-onset-before-20261029。九文件register-board.patch干净应用已验证，八个overlay与runtime一致，config.h的START/MAX均80。离线BOOT诊断音量片段仍40，当前正常网络构建未启用该模式。

此前阶段记录：完整语音138项通过（包含Breeze39项）；后端智能体42项通过，扩大一般问答后语音路由5项通过；真实模型身份、缺站号澄清、P1短摘要、一般知识追问和数学连续问答通过。完整合成OTA/WS/ASR/LLM/TTS链路通过；该报告在最后的通用知识范围扩展之前，最后范围另有真实模型和单测验证。report.json等汇总已复制到server，原始非测试麦克风转录只留D:/ut-voice，不写入仓库报告。仍需距离/噪声/误唤醒、受控P1准确率、长期断网测试；AEC未启用。

恢复前核对进程命令、端口和创建时间；语音端口默认8941/8942，按现场地址配置防火墙。USB串口与设备MAC重新发现。viewer/device凭据只存服务器私有目录，DeepSeek Key只存backend/.env；不放入固件或发布包。串口观察测试结束后已释放。

本文件记录发布前的联调快照；GitHub提交及合并状态以仓库历史为准。
