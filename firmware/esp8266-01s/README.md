# ESP8266-01S 本地 MQTT 串口桥

> **当前台架版本（2026-09-28）**：Node A/B 与双 ESP 已接入 31 路传感器，项目负责人已确认当前范围验收。可烧录源码、当前引脚表及全传感器记录位于 [功能分支](https://github.com/x1ng-chen/utility-tunnel-digital-twin/tree/feature/dual-screen-joystick-menu)，接线以 [9 月 27 日冻结表](https://github.com/x1ng-chen/utility-tunnel-digital-twin/blob/feature/dual-screen-joystick-menu/docs/hardware/2026-09-27-双节点台架外部传感器接线冻结.md)为准。下文保留 main 的早期接口/构建说明，不应当作当前台架完整接线或烧录指令。详见 [当前状态](../../docs/项目当前状态.md)。

该固件用于项目既定链路：`STM32 -> ESP8266 -> 本地 MQTT -> IoTDA 网关 -> 华为云`。ESP-01S 不保存华为云设备密钥，也不通过公网明文连接 IoTDA。

## 接线与供电

烧录时使用 **3.3 V 电平** USB-TTL，ESP-01S 需要独立、稳定的 3.3 V 电源（建议持续 500 mA 以上余量），所有设备共地。不得把 5 V 接到 VCC、EN、RX 或 GPIO。

| ESP-01S | USB-TTL / 电源（烧录模式） |
|---|---|
| VCC | 稳定 3.3 V |
| GND | GND |
| EN/CH_PD | 3.3 V |
| TX | USB-TTL RX |
| RX | USB-TTL TX（3.3 V） |
| GPIO0 | GND（仅上电/复位进入烧录时） |
| GPIO2 | 3.3 V 上拉 |
| RST | 3.3 V 上拉；短接 GND 可复位 |

烧录完成后先断电，将 GPIO0 从 GND 断开，再重新上电运行。

## 配置、编译和烧录

1. 将 `include/secrets.example.h` 复制为 `include/secrets.h`，只填本地 Wi-Fi 和本地 MQTT Broker；不要写入华为云密钥。
2. 执行 `pio run` 编译。
3. ESP-01S 进入烧录模式后执行 `pio run -t upload --upload-port COMx`。
4. GPIO0 恢复高电平并重启，执行 `pio device monitor -p COMx -b 9600`。

串口输入 `STATUS` 可查看 Wi-Fi、IP、RSSI、MQTT 和可用堆。STM32 发送一行 `ut.telemetry.v1` JSON 后，固件发布到 `ut/v1/CTRL-01/telemetry`；收到的命令以 `MQTT|topic|payload` 格式转发给 STM32。
