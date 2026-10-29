# 专用语音板接线：你好，小管 / 小管

用户已确认：ESP32-S3 N16R8 专门用于语音，不承担 RS-485 网关。唤醒词是“你好，小管 / 小管”，拼音 `ni hao xiao guan / xiao guan`。
麦克风接线和离线唤醒已完成实物测试，记录见 [实物测试](../firmware/xiaozhi/device-test.md)。功放/喇叭已按下表接线并通过手动短音测试，用户确认音量 20 合适且清楚，见 [喇叭测试](../firmware/xiaozhi/speaker-test.md)；OLED 已按下表加入并通过文字/状态显示测试。引脚名称按开发板丝印的 GPIO 数字识别，不按照片方向数排针。

## 首次离线采音 / 唤醒（历史阶段）

喇叭参数和屏幕型号暂时找不到。本机已只接麦克风与 USB 完成首次测试，共观察到三次唤醒，其中两次连续触发。复现时**只需接麦克风六根线和 USB 数据线**。功放、喇叭、屏幕和其他传感器先不接。
历史离线固件配置启用 `CONFIG_UTILITY_TUNNEL_OFFLINE_WAKE_TEST=y`：从本地资源加载中文模型，串口每约一秒打印 `OFFLINE MIC` 的 samples/rms/peak，检测到唤醒后打印 `OFFLINE WAKE DETECTED`。首次固件 BOOT 只重新启用检测。该阶段另启用 `CONFIG_UTILITY_TUNNEL_SPEAKER_TEST=y`：短按 BOOT 播放一次约540ms提示音；开机不播放，唤醒会用少女音在本板回答“我在呀，你说！”；仍不启动网络、OTA 或问答协议。

RMS/peak 是转换后的数字采样幅度，不能当作校准声压值。用户已确认功放/喇叭为卖家配套，已进行输出测试；当前联网语音已通过实测，运行音量80；下文保留首次接线阶段的说明。

## 实物识别

| 照片 | 模块 | 确认程度 / 用途 |
|---|---|---|
| 1、2 | ESP32-S3 DevKitC-1 风格双 USB 核心板 | 实际识别 ESP32-S3、16MB Flash、8MB PSRAM；厂商版本未确认 |
| 3、4 | I²S 数字麦克风 | 能看到 L/R、WS、SCK、SD、VDD、GND；外形类似 INMP441，芯片标识未确认 |
| 5 | 四针 I²C OLED | 0x3C 响应，SSD1306-compatible 128×32 布局显示正常；准确芯片型号未确认 |
| 7 | MAX98357A I²S 功放 | 丝印可辨认；板载电阻与增益未测量 |
| 10 | 两线无源喇叭 | 用户确认卖家与功放配套；已听到清楚提示音，Ω/W 未知 |
| 6、8、9 | 测距类模块、MPU-6050、薄膜压力传感器 | 不接入第一版语音链路 |

主板已有 BOOT 键；历史离线固件用它触发短提示音测试。不连接额外触摸、音量按键，不注册参考面包板的 GPIO18 演示灯控。

## 麦克风 → ESP32-S3

适用于照片所示接口，**以卖家确认的 INMP441 或兼容 I²S 左声道模块为前提**。若实际芯片需要其他时序，再调整驱动。

| 麦克风丝印 | 接主板 | 用途 |
|---|---|---|
| VDD | 3V3 | 3.3V 电源，不能接 5V |
| GND | GND | 共地 |
| WS | GPIO4 | 输入字选择时钟 |
| SCK | GPIO5 | 输入位时钟 |
| SD | GPIO6 | 麦克风数据输出，接主板输入 |
| L/R | GND | 固定左声道，不悬空 |

INMP441 的 L/R 低电平选左声道，与本板使用的左槽一致。输入 16 kHz；I²S 使用 32 位槽接收，复用上游数字麦克风转换路径。若模块未自带 SD 下拉，应按数据手册补 100kΩ 到 GND；供电去耦以模块原理图为准。

## MAX98357A → ESP32-S3 / 喇叭

先断开 USB 再接线。初次使用同一 USB 电源给整套模块供电；先确认开发板丝印 5V 引脚是 USB 5V 电源轨。所有模块 GND 共地。

| 功放丝印 | 接到 | 用途 |
|---|---|---|
| VIN | 主板 5V | 功放供电；不由主板 3V3 稳压输出承担喇叭负载 |
| GND | 主板 GND | 共地 |
| DIN | GPIO7 | 主板音频输出 |
| BCLK | GPIO15 | 输出位时钟 |
| LRC | GPIO16 | 输出字选择时钟 |
| SD | 主板 3V3 | 启用并选择左声道；这是功放的 SD/MODE，不是麦克风 SD 数据脚 |
| GAIN | 不接外线 | 保留模块增益设置；不能仅凭照片确定其板载电阻和实际 dB |
| 绿色端子 + / − | 喇叭两根线 | 红线接 +、黑线接 −；按模块实际端子标记为准 |

喇叭两端**都不能接主板 GND**，这是桥接输出。按模块说明使用至少 4Ω 的动圈喇叭，额定功率仍需确认。SD 的电压不能超过功放供电允许范围；不要让功放单独断电、SD 仍由另一电源保持高电平。

当前按用户要求将开机和回应数字音量设为40，运行音量限制在0–40；此前音量20的喇叭实测记录保留。这是调试设置，**不能代替喇叭额定功率和阻抗核验**。

功放输出选 **48 kHz**，没有照搬参考板的 24 kHz：MAX98357A 手册未支持 24 kHz LRCLK；本地 16kHz Opus 短音经重采样到 48kHz 已能播放；服务端语音仍需单独联调。麦克风、功放各用一组独立 I²S 时钟，不共用 BCLK/WS。

## 小屏当前接法（已完成显示测试）

| OLED 丝印 | 当前连接 |
|---|---|
| GND | GND |
| | 3V3 |
| SDA | GPIO41 |
| SCL | GPIO42 |

外形接近 128×32 的小屏，仍不能确认 SSD1306 或分辨率。I²C 地址扫描只能确认响应地址，不能可靠识别控制器/分辨率。当前已通过 0x3C 探测、SSD1306-compatible 128×32 布局的文字/状态显示和自动恢复待机测试，详见 [OLED 实测](../firmware/xiaozhi/oled-test.md)。

## 3V3 引脚不足时分电

用面包板同一数字行 a～e 的五个相通孔分电，例如 a5 接主板 3V3、b5 接麦克风 VDD、c5 接功放 SD、d5 接 OLED VCC。GND 另行共地；功放 VIN 仍接 5V，不与上述 3V3 组混接。先断开 USB 再调整接线。

## 接线与验收顺序

1. 首次断电只接麦克风，按上表复核 3V3、GND、WS、SCK、SD、L/R；功放和喇叭留到后续输出测试。
2. 只把这块语音新板通过带数据功能的 USB 线接电脑，识别 USB 串口、芯片、Flash/PSRAM；记录串口，避免选中 RS-485 网关板。
3. 备份现有 Flash/配置，再烧录**已经构建核对的**专用固件；烧录资源和构建状态见固件说明，不能只凭配置文件判断固件可用。
4. 离线先看安静/说话时的 RMS、peak 是否变化，再连续测试“你好，小管 / 小管”；记录误唤醒/漏唤醒，阈值 20 只是初值。随后用配套功放/喇叭独立测试短提示音，逐档调节音量。
5. 配置自己的语音服务地址、设备鉴权和 ASR/TTS，再联通 Django 只读数据查询；不把网页后台密码或 DeepSeek Key 放到板上。
6. 验收断网恢复、过期凭证、重复唤醒、停止播报和迟到回答；未验证回声消除，不承诺边播边听。

N16R8 的 Octal PSRAM 会占用 GPIO35–37；本方案避开这些脚，同时保留 GPIO19/20 的原生 USB 用途。板载 LED 在不同开发板版本上可能位于 GPIO38 或 GPIO48，首版暂不驱动它。

## 配置与资料

- 当前用户硬件记录：[`hardware-profile.json`](../hardware-profile.json)
- 固件板级与构建说明：[`firmware/xiaozhi/README.md`](../firmware/xiaozhi/README.md)
- [Espressif DevKitC-1 v1.1 指南](https://documentation.espressif.com/esp-dev-kits/en/latest/esp32s3/esp32-s3-devkitc-1/user_guide_v1.1.html)
- [TDK INMP441 数据手册](https://product.tdk.com/system/files/dam/doc/product/sw_piezo/mic/mems-mic/data_sheet/inmp441.pdf)
- [ADI MAX98357A/B 数据手册](https://www.analog.com/media/en/technical-documentation/data-sheets/MAX98357A-MAX98357B.pdf)
- [Adafruit MAX98357 模块引脚与扬声器说明](https://learn.adafruit.com/adafruit-max98357-i2s-class-d-mono-amp/pinouts)
- [所参考的固定版本引脚配置](https://github.com/78/xiaozhi-esp32/blob/c435f99a88066029ec2dbd2d758c8cc9d051565b/main/boards/bread-compact-wifi/config.h)

新版少女音回应“我在呀，你说！”与音量40的烧录/试听状态见 [当前回应记录](../firmware/xiaozhi/wake-ack-test.md)。


新版已通过四静态镜像校验，用户确认两次回应正常、音量40合适；同次启动两轮恢复监听和OLED待机也已记录。见 [新版实测](../firmware/xiaozhi/breeze-playful-test-report.json)。
