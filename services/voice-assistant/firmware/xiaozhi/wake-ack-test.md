# 少女音本地唤醒回应（2026-10-27）

当前已采用Breeze TTS 2俏皮少女音 guanlang_playful_girl。说“你好管廊”后回答一次“我在呀，你说！”，音量40。用户确认两次都正常，新声音和音量合适。

新版仅更新应用分区并通过四个静态镜像校验，模型资源和运行OTA记录保留。串口记录同一次启动内两轮唤醒、播放、排空、重新监听、OLED回待机；每轮41个60ms帧，未观察到重启、播放超时或致命错误。排空并关闭输出后2.13–2.14秒回到待机。人工试听与串口证据分别保存。

- Ogg Opus：48kHz单声道，有效2.40秒；固件整包播放2.46秒。
- PCM增益0.658915，响度匹配旧回应；保留语调起伏，数字音量40。
- 回应期间暂停检测；排空并等待300ms后恢复监听。BOOT保留原短提示音，开机不自动播放。
- OLED同步显示新回应。本地按文字描述设计音色，无用户录音或云合成；模型及输出受BreezeBlue研究和非商业许可约束。

[当前构建](breeze-playful-build-report.json) · [当前实测](breeze-playful-test-report.json) · [音频来源](overlay/main/boards/utility-tunnel-s3/ut_wake_ack.audio.json) · [音色包](../../voices/breeze-guanlang-playful-girl/manifest.json)

Huihui旧版[构建](huihui-wake-ack-build-report.json)、[实测](huihui-wake-ack-test-report.json)与[文字记录](huihui-wake-ack-test.md)保留为历史。旧固件和音频回滚副本保存在仓库外 D:/ut-voice/rollback/huihui-wake-volume40-20261027。

当前仅验证专用板离线固定回应。完整联网ASR、Agent、TTS问答尚待接入；联网流程需保证本地回应播完再开始上传，并避免与服务器开场语重复。
