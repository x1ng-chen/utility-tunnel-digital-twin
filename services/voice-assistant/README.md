# ESP32-S3 小管语音助手

当前界面：128×32 OLED 待机时只显示全屏双眼并缓慢眨眼；聆听和连接时双眼缩小至左侧，右侧显示状态与字幕；播放回答时隐藏所有文字，右侧切换为嘴巴开合和声波条动画。状态改变时眼睛移动约300毫秒。用户已确认待机、对话布局以及无文字的说话动画均正常。

音量支持“音量调到50”“声音大一点”“声音小一点”“静音”“取消静音”等；联网聆听时由受限语音服务识别并读取设备实际值，播报中可说“声音大一点/小一点”本地调节。范围0–80，重启保留上次音量；0为静音，取消静音恢复此前非零音量。设备只暴露读取和设置喇叭音量的两个专用工具；不开放管廊设备控制。用户已实测从80调到50、再调大成功。

当前状态（2026-10-29）：DeepSeek 已接通，支持日常问答、一般知识、连续追问和管廊只读查询；Breeze少女音保持不变。音量现支持语音调节并记忆上次设置，用户确认连续回答和调音正常。

AI查询次数限制已按用户要求关闭（AI_ASSISTANT_RATE_LIMIT=none），仍需登录鉴权；模型服务自身的限流与账户额度照常适用。

待机可说“你好，小管”或“小管”。听完“我在呀，你说！”后提问，回答后可直接追问；需要停止时说“不用说了”或“闭嘴”，它会本地回答“好的，需要时请随时叫我”并回到待机。旧唤醒词已停用。

本轮优化：明确站点/设备拼写会正规化（P一→P1、一号检测点→P1检测点、MQ二零一→MQ2-01），缺失编号不猜补；语音适配器不再为任何回答自动添加固定核查开场；具体数据缺失或限制由回答本身说明。网络唤醒回应尾音等待从300ms缩至150ms，热麦克风省去重复120ms等待，冷输入保留原流程。真实P1语音识别准确率仍需受控录音评估，不能用文本纠正测试代替。

当前129项语音回归与275项此前后端全量检查通过（含7项语音路由/不限次回归）。此前的一般知识、数学连续问答及完整合成音频链路验证记录保留供参考。汇总见 [本轮验证](server/voice-quality-test-report.json)，固件见 [当前停止控制构建](firmware/xiaozhi/stop-states-build-report.json)。

固定开场修正见 [真实问答验证](server/no-prefix-test-report.json)：聊天、知识解释和站点查询均无自动前缀，原数据时间、未知状态与必要限制保留。

接线见 [硬件说明](hardware/README.md)，本机状态见 [硬件配置](hardware-profile.json)，构建复现见 [固件说明](firmware/xiaozhi/README.md)，恢复运行见 [联调断点](server/CONTINUE.md)。

## 第一版结构

```text
ESP32-S3：离线自定义唤醒 → 麦克风采音/编码
  ↕ 小智固件的音频传输协议
自建 xiaozhi-esp32-server：ASR → 本目录适配器 → TTS
  ↕ 带查看者凭据的 HTTP / HTTPS
现有 Django /api/assistant/chat/ → 现有 DeepSeek 工具 Agent
  ↕
管廊台账、遥测、告警、工单只读查询
```

固件建议基于 `78/xiaozhi-esp32` 适配实际音频板；语音服务建议复用 `xinnan-tech/xiaozhi-esp32-server`。本目录提供管廊LLM桥接与本地TTS适配器，音频传输由独立语音服务器负责。

## 已完成的软件部分

- 将 ASR 最终文本和普通对话历史转成现有管廊 API 的消息契约；丢弃外部 system/tool 消息及其附带的工具数据。
- 每次查询先验证账号为 viewer；只访问身份与 Agent 两个固定端点。
- 禁止重定向、关闭环境代理转发，非回环 API 地址要求 HTTPS；令牌仅从服务器环境读取。
- 不播报工单草案为已执行结果。已有网页仍负责审阅/确认工单，语音无硬件控制接口。
- 区分数据库查询与未查询现场的解释；异常转成可朗读的中文提示，不回传凭据或服务错误原文。

## 自测

Python 3.12或以上。基础桥接测试只用标准库；完整原生音频测试需安装server/requirements-selected.txt中的运行依赖、Opus DLL和soxr==1.1.0。

```powershell
python -B -m unittest discover -s services/voice-assistant/tests -v
```

测试使用内存响应和合成PCM，不访问真实模型、麦克风或生产写入接口。当前完整语音回归129项通过（包含Breeze39项）；原生编解码用例检查采样时长、频率与尾帧。

## 接入自建语音服务器

1. 先按上游说明安装并独立跑通 ASR、TTS 和设备鉴权，记录实际使用的固件/服务端 commit。
2. 将 `xiaozhi_adapter/utility_tunnel/` 整个目录复制到语音服务器的 `core/providers/llm/utility_tunnel/`，不要覆盖上游其他 provider。
3. 将 `xiaozhi-config.example.yaml` 片段合并到上游 `data/.config.yaml`。使用 `Intent: nointent`、`Memory: nomem`，工具查询由 Django Agent 负责；不启用管廊控制的外部 MCP/意图插件。
4. 在语音服务器进程环境设置 `.env.example` 所列变量。此适配器不自动读取 `.env`。使用现有查看者账号的临时 token 进行开发联调，不把后台管理员密码、DeepSeek Key 或遥测接入 Key 放进板端。
5. 语音网关使用独立viewer会话并自动续期；设备使用可撤销的独立绑定凭据。账号凭据只存服务器私有文件，板端不持有Django账号或DeepSeek Key。
6. DeepSeek 仍由 Django 配置。ASR、TTS 必须另外配置并说明数据去向；这一步尚未替用户选择或调用付费语音服务。
7. 本机 Django 已占用 8000，示例语音 WebSocket/HTTP 分别使用 8941/8942。板端连接的是电脑/服务器局域网地址，不是板端自己的 127.0.0.1；对外部署使用已配置鉴权的 WSS/HTTPS 地址。

## 自定义中文唤醒词

上游当前 `USE_CUSTOM_WAKE_WORD` 使用 MultiNet，支持 ESP32-S3+PSRAM；中文用空格分隔拼音，并有独立显示文本与阈值配置。WakeNet 定制模型是另一条路线，不能把任意中文字符串当作已训练好的 WakeNet 模型。

已在 `hardware-profile.json` 记录用户确认项与待核实项，并准备独立的 `utility-tunnel-s3` 板级：麦克风 GPIO4/5/6，功放 GPIO7/15/16；输入 16 kHz、输出 48 kHz。`firmware/xiaozhi/sdkconfig.voice.defaults` 已填写“你好，小管”的中文/拼音、MultiNet7 中文模型和默认资源打包选项，阈值 20 只是初值。固件源码固定到 `upstream.lock.json` 的 commit；模型资源已通过打包检查，并在实物上成功加载与触发。N16R8 的容量不能证明音频电路兼容，自定义词的误唤醒率、漏唤醒和播报回声仍需实物验证。

`hardware-profile.example.json` 保留为空白模板供其他硬件使用，本机这块语音板以 `hardware-profile.json` 为准。

## 当前实物进度与后续

已验证：8MB PSRAM、数字麦克风、OLED文字和状态、本地少女音回应、认证OTA/WS、真实问答、P1查询、原生PCM流式，以及两个停止词和停止后重新唤醒。输入16kHz、输出48kHz。

播报中或回答后继续监听时，说停止词均会播报本地确认并回到待机，两种场景已由用户复测通过。停止期间关闭远端音频门禁、清理解码队列、关闭旧WebSocket，并用代际校验丢弃迟到任务。后台阻塞查询不保证立即取消，但旧结果不会继续播放。新的短唤醒词在Speaking状态不重新开启对话，避免喇叭自称“小管”导致自我唤醒；停止命令检测仍保持开启。

后续测试包括不同距离/噪声下的命中率和误触发、断网恢复、长期凭据轮换。AEC未开启。工单确认仍在网页完成。

## 参考与兼容性边界（2026-10-26 核对）

- 小智固件及功能：https://github.com/78/xiaozhi-esp32/blob/main/README_zh.md
- 板级适配：https://github.com/78/xiaozhi-esp32/blob/main/docs/custom-board_zh.md
- 唤醒配置：https://github.com/78/xiaozhi-esp32/blob/main/main/Kconfig.projbuild
- 自定义唤醒实现：https://github.com/78/xiaozhi-esp32/blob/main/main/audio/wake_words/custom_wake_word.cc
- 语音服务器 provider 接口：https://github.com/xinnan-tech/xiaozhi-esp32-server/blob/main/main/xiaozhi-server/core/providers/llm/base.py
- 语音服务器配置：https://github.com/xinnan-tech/xiaozhi-esp32-server/blob/main/main/xiaozhi-server/config.yaml

上游main仍会变化；当前部署固定commit，已在本机受限网关及专用ESP32实物集成通过。迁移服务器后须重新核验网络和音频链路。

当前显示接线与实测见 [OLED 测试记录](firmware/xiaozhi/oled-test.md)；电脑端依赖、模型与离线验收见 [本机语音组件](server/NOTES.md)。本机已完成Key、viewer自动续期、设备准入和板端问答；私有凭据不进入仓库。

当前唤醒回应与音量设置见 [少女音固件记录](firmware/xiaozhi/wake-ack-test.md)。

## 发布与下载

本目录随项目 main 分支发布。完整源码可从 GitHub 的 Code → Download ZIP 下载；需要模型大文件时请使用 Git LFS 克隆并执行 git lfs pull。语音模型权重与本机私有配置不包含在源码包内，依赖下载来源及哈希见各 lock 文件。

迁移时先阅读 server/NOTES.md 和 firmware/xiaozhi/README.md，按 .env.example 创建服务器私有配置，重新配网和绑定专用设备。第三方许可见 [NOTICE](NOTICE.md)；Breeze 音色和生成音频按其来源许可使用。
