# 本机 Breeze TTS 适配器与少女音

实现依据：HoppouAI/Breeze-TTS-2.cpp v0.1.3 的原生 HTTP speech 接口。
本次仅本地试听与开发；不声明模型权重具备商用许可。

文件：将 xiaozhi_adapter/breeze_local.py 与 breeze_client.py 同时复制到运行服务的 core/providers/tts/。
2026-10-28：已部署原生PCM流式适配器，Breeze监听127.0.0.1:7861，专用语音网关在受限局域网运行。少女音guanlang_playful_girl、音量40、真实板端问答和连贯流式播放均通过。

当前本机选用配置片段（迁移时合并，不要覆盖上游完整配置）：

```yaml
selected_module:
  TTS: BreezeLocal
TTS:
  BreezeLocal:
    type: breeze_local
    base_url: http://127.0.0.1:7861
    voice_id: guanlang_playful_girl
    stream_pcm: true
    tts_timeout: 45
    max_text_chars: 2000
    max_frames: 750
    max_audio_bytes: 8388608
```

Breeze 应仅绑定 numeric loopback；可关闭其单独 WebSocket listener（--ws-port -1）。
客户端仅接受带显式端口的 numeric loopback HTTP URL，不使用环境代理，不跟随重定向。
不发送鉴权占位 Key，不上传参考录音，文本仅以原生表单 text 发送。
voice_id 来自可信配置；缺失的 saved voice 返回明确错误，不回退 SAPI 或随机设计音色。
真实试听后，应先用本机 GET /v1/voices/guanlang_playful_girl 确认 saved=true；本客户端不自动注册、覆盖或删除音色。

每个片段只 POST 一次 /v1/audio/speech，表单包含 text、voice_id 与 max_new_tokens 帧数上限。
不使用会默认重试409的OpenAI SDK。409立即返回 busy，不自动重试；
provider 同时覆盖小智 base 的 to_tts_stream / to_tts，避免外层五次重放。

原生成功响应须为 audio/pcm、X-Sample-Rate=24000、X-Sample-Format=s16le。
响应为无头24kHz mono PCM16。默认路径保持一个soxr重采样器和Opus编码器，凑足60ms帧立即交付；仅成功EOF冲洗尾帧，取消/旧句子不补发。显式stream_pcm=false保留分句WAV兼容路径，文件API仍生成正确WAV头。
不要复用 SAPI 客户端固定16kHz的校验函数，也不要把原始PCM直接当WAV。

max_frames 同时限制发送给模型的 max_new_tokens，并按每模型帧1920个24kHz样本限制累计PCM。
默认750帧对应最多60秒/2880000字节；实际限制为该值与 max_audio_bytes 的较小者。
总期限包含连接和读流；固定输入长度、非空/偶数字节音频、格式、累计字节和帧数均检查。
原子写文件：验证及取消检查通过后才替换目标，不留下半成品。

取消、连接停止或 current_sentence_id 失效会关闭本次HTTP连接，清除未交付音频；
不会终止共享Breeze进程。服务端到下一次chunk写出失败时才可能停止计算，取消后短暂409仍属可能。
队列包始终携带旧片段捕获的句子ID，不能将旧音频重新标为新轮次。

完整性边界：v0.1.3会吞掉部分生成异常后正常结束chunked响应。因此200、偶数字节和干净EOF
只能证明传输/PCM格式有效，不能保证整句话无漏字。可检测的传输中断、奇数尾字节及超限均拒绝；
不能把该客户端的成功响应当成语义完整性证明。动态生成内容仍需真实试听及辅助ASR确认。

专项测试使用内存HTTP响应，不连接真实Breeze，无云服务、麦克风、串口或持久服务进程。
真实验证使用旧候选 guanlang_female：saved voice存在性、24kHz WAV、单次HTTP和26个60ms Opus包契约通过。短句HTTP用时约1.4秒，provider约0.8秒，不代表长文本性能。详见 [真实验证报告](breeze-http-test.json)。

HTTP WAV辅助ASR为“我在”；另一次provider生成音频经Opus解码被识别为“我在我在”，该观察原样保留。对HTTP WAV做独立离线Opus往返后ASR仍为“我在”，不能据此判定另一次生成的主观质量。当前另选俏皮少女音guanlang_playful_girl，本地CLI生成和板端固定回应两次试听已通过。历史HTTP报告仍对应旧候选，此为历史阶段结论；后续少女音联网问答与原生流式已通过，见native-pcm-stream-test.json及native-pcm-roundtrip-test.json。

## 当前启用方式

当前首选音色与哈希见 [音色配置](preferred-voice.json)，本机配置变更见 [准备记录](preferred-voice-setup.json)。同一音色的固定回应已通过 [板端实测](../firmware/xiaozhi/breeze-playful-test-report.json)。

在PowerShell检查启动条件：

    & 'D:\新建文件夹\utility-tunnel-digital-twin\services\voice-assistant\server\start-breeze-local.ps1' -CheckOnly

需要运行Breeze时，去掉CheckOnly。脚本前台管理一个隐藏子进程，仅监听127.0.0.1:7861，并关闭额外WebSocket；Ctrl+C只停止本次启动的子进程，不结束其他Breeze进程。发现端口占用或CLI正在生成时会退出。可选VerifyModelHash校验全部权重，可选Cpu使用CPU。

当前已实际运行Breeze和受限网关并完成实物问答；CheckOnly仍只检查启动条件。GPU运行需本机Vulkan支持，迁移服务器时需重新安装对应运行时与权重，并保留相同音色文件、来源和许可。

本机已完成DeepSeek、独立viewer自动续期、设备准入和联网音频联调。迁移时重新配置服务器私有凭据；预检不会开放局域网。
