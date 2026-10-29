# 受限语音通路的合成音频测试

test_voice_roundtrip.py 默认只检查本机现有WAV和准备的协议，不发OTA、WS、ASR、LLM或TTS请求，也不启停任何服务。只有显式加 --run 才执行一次真实请求；执行由主任务在gateway ready后决定。

默认输入为 D:/ut-voice/tts-test/windows-sapi-test.wav，已有本地SAPI测试音频，16kHz、mono、PCM16、3.93秒；预期文本“你好这是管廊本地语音测试”。不重新合成输入，也不播放电脑麦克风或扬声器。

私有设备文件固定在D:/ut-voice/private/voice-device.json，格式为ut.voice.devices.v1及一个devices条目。Device-Id、Client-Id和64hex设备token仅在内存中构造请求头，绝不进入输出或报告。OTA仅允许127.0.0.1:8942/xiaozhi/ota/，返回WS URL必须精确匹配127.0.0.1:8941/xiaozhi/v1/，token一致且version=1；不接受固件更新URL、外部URL或重定向。

准备检查：

    & 'D:/ut-voice/voice-server-venv/Scripts/python.exe' -B 'D:/新建文件夹/utility-tunnel-digital-twin/services/voice-assistant/server/test_voice_roundtrip.py'

真实测试（会调用一次已配置的语音问答链路）：

    & 'D:/ut-voice/voice-server-venv/Scripts/python.exe' -B 'D:/新建文件夹/utility-tunnel-digital-twin/services/voice-assistant/server/test_voice_roundtrip.py' --run

hello使用Opus/16kHz/mono/60ms，关闭MCP和AEC。确认hello后稍作初始化等待，再发送manual listen-start，按60ms节奏发送原生Opus帧，附加300ms尾静音与队列排空等待后listen-stop。测试不用text/detect绕过ASR。

输出置于D:/ut-voice/integration-output/roundtrip-日期-随机串/，含report.json和reply.wav；未完成TTS时只能生成reply.partial.wav。只记录输入/输出格式、哈希、STT、可播报回复、状态与耗时，不记录设备ID、Client-Id、token、会话ID或原始控制报文。

上游type=llm消息是情绪emoji信号；实际口头回复来自tts/sentence_start文字，报告明确区分。必须收到STT、LLM信号、TTS stop、非空回复和有效音频；ASR相似度至少0.85，所有Opus包必须原生解码为60ms PCM，错误回退回复不算通过。

总超时默认120秒，可选30–180秒；单包最多2048字节，最多1000个回复包（60秒）。finally仅关闭本客户端连接并释放本客户端编解码器，不终止任何服务。该测试只能证明电脑端合成音频的协议链路，不能代表物理ESP32、真实麦克风噪声或喇叭播放已通过。
