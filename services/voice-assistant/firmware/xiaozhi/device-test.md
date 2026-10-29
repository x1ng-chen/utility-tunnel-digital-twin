# ESP32-S3 “你好管廊”实物测试

日期：2026-10-26（Asia/Shanghai）。当前是**离线采音/唤醒测试**，联网问答和语音播放仍待接入。

| 检查 | 结果 |
|---|---|
| 串口与芯片 | COM5，ESP32-S3 rev v0.2 |
| 存储容量 | 16MB Flash；8MB Octal PSRAM 初始化成功，80MHz |
| 原固件备份 | 完整 16,777,216 字节，与设备摘要校验一致；备份留在仓库外 |
| 固件烧录 | bootloader、分区表、OTA 初始数据、应用、模型资源五段全部验证通过 |
| 中文模型 | `mn7_cn`、`fst` 成功加载，词条为 `ni hao guan lang` / “你好管廊” |
| I²S 麦克风 | 持续取得每秒 16,000 个采样，RMS/peak 随现场声音变化 |
| 唤醒 | 共记录三次成功事件；最后两次未重启板子，连续触发及重新启用检测通过 |

关键日志：

```text
I (59220) Application: OFFLINE WAKE DETECTED: 你好管廊
I (749040) Application: OFFLINE WAKE DETECTED: 你好管廊
I (764610) Application: OFFLINE WAKE DETECTED: 你好管廊
```

检测分数分别为 0.215499、0.262111、0.258016，当前阈值为 0.20；这些分数不是成功率。
第二轮空监听时，用户确认没有再次说词，不计漏检。三次事件证明基本采音、识别及恢复监听流程可用；距离、噪声和误唤醒率仍需进一步测试。

完整串口日志位于本机 `D:\ut-voice\`：
- `device-boot-20261026-224101.log`：启动、PSRAM、模型、采音和首次唤醒。
- `device-repeat-20261026-224800.log`：用户未说词的空监听窗口。
- `device-repeat-20261026-225241.log`：同次启动中再触发两次，串口观察自动结束。

备份位于 `D:\ut-voice\backups\`，私人烧录/备份元数据为 `D:\ut-voice\device-flash-report.json`；不将原始 Flash/NVS 或备份内容加入 Git。
本轮 921600 波特率读取出现串口错误，改为 460800 完成备份、写入及验证；没有整片擦除或改写 eFuse。

当前串口观察进程已退出，固件仍在新板上运行；USB 供电时继续离线监听。当前反馈输出到串口，功放、喇叭、屏幕以及 ASR/TTS/管廊语音服务未纳入这次验收。

结构化记录见 [device-test-report.json](device-test-report.json)。构建快照 `build-report.json` 和先前分发的固件包保持原样；当前硬件状态以本记录和 [hardware-profile.json](../../hardware-profile.json) 为准。
