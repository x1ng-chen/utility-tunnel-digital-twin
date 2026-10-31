# 本机语音服务组件验收

固定服务端：xinnan-tech/xiaozhi-esp32-server commit a377d89dcd58e6e18417a57e9357c0dd23657746。
原始归档保留；运行副本 D:\ut-voice\server，独立 Python 3.12.14 环境 D:\ut-voice\voice-server-venv。
本目录不包含私有配置、设备鉴权密钥、查看者令牌或 DeepSeek Key。

已安装与验证：
- CPU ONNX Paraformer 中文 ASR；官方 0.wav 与本机 SAPI 合成短句均有有效识别。
- 历史Windows SAPI Huihui组件已验证并保留；当前首选已切换为BreezeLocal/guanlang_playful_girl，见 [Breeze说明](breeze-local.md)。
- Silero ONNX CPU 模型：静音与合成语音区分通过，实际 provider.is_vad 契约通过。
- 原生 libopus 1.6.1 编解码 960 样本通过；FFmpeg 7.1 可执行。
- pip check、固定源码 app 导入、选定 ASR/TTS/VAD provider 导入及实际契约通过。
- app 仅导入，没有调用 main、监听端口或创建持久服务；没有连接 Django / DeepSeek。
- 本次按实际缺失补充 PyYAML==6.0.3；其余依赖沿用独立语音环境。

复现文件：
- requirements-selected.txt：本机选用的直接依赖；requirements.lock：实际完整冻结版本。
- sources.lock.json：固定服务端、模型、VAD、Opus、FFmpeg 与适配器来源及 SHA-256。
- components-test.json：不含凭据的本机测试记录。
- verify_components.py：会创建报告/临时本机日志；禁止外联，仅允许 Windows asyncio 内部回环连接。
- preflight.py：只做本地检查，不启动服务。加 --require-agent-token 才要求临时查看者令牌已配置。

私有运行配置位于 D:\ut-voice\server\data\.config.yaml；文件 ACL 已收紧为当前用户。
配置仅监听 127.0.0.1:8941 / 8942，板子当前无法通过局域网访问。
设备鉴权已启用，但固定上游的简单 OTA 可为传入的 device-id 签发 token，Vision 还有测试客户端旁路；
这尚不构成已审核的设备准入。开放局域网前须另审 OTA 准入并关闭/拦截 Vision 路由。
提示词模板仅保留 {{ base_prompt }}，避免上游默认模板隐含定位、天气或额外上下文请求。

运行时只在该进程前置 venv 的 Scripts 到 PATH，以发现 opus.dll 和 ffmpeg.exe；不要改机器全局 PATH。
未创建查看者 token；现有桥接只允许 viewer，token 默认 900 秒到期。
DeepSeek Key 由用户稍后本机填写；当前没有 Agent 调用或付费云请求。
LLM provider 在缺少查看者令牌时会拒绝初始化，这是当前刻意保留的启动前条件。

尚未验证：真实麦克风 ASR、ESP32 联网音频、联网动态合成语音经板端喇叭播放、连续对话、
断网重连、设备准入、查看者凭据生命周期以及 Django Agent 端到端回答。
ASR 从合成测试句得到“你好这是管廊本地语音测试”，不能等同于真实噪声环境准确率。

OLED 硬件文字与状态显示另已通过 [板端实测](../firmware/xiaozhi/oled-test.md)，不属于本目录电脑端组件测试的范围。

当前固定少女音回应已在板端通过两轮播放、恢复监听及OLED待机实测；这与联网动态TTS验收分开记录。Breeze适配器26项测试通过，本机preflight及启动脚本CheckOnly通过；未配置Agent查看者令牌、未启动常驻服务。
