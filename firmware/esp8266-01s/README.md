# ESP8266-01S 本地 MQTT 串口桥

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

1. 将 `include/secrets.example.h` 复制为 `include/secrets.h`，只填本地 Wi-Fi 与可选的本地 MQTT 用户名/密码；不要填写电脑 IP，也不要写入华为云密钥。
2. 按设备选择构建：`pio run -e esp01_ctrl01` 或 `pio run -e esp01_ctrl02`。
3. ESP-01S 进入烧录模式后执行 `pio run -e esp01_ctrl01 -t upload --upload-port COMx`（第二块改为 `esp01_ctrl02`）。
4. GPIO0 恢复高电平并重启，执行 `pio device monitor -p COMx -b 9600`。

电脑上的 IoTDA 网关会每 3 秒向 UDP `4210` 广播本地 MQTT 服务。ESP 使用广播包的来源 IP 与其中的端口连接 Broker，因此手机热点重新分配电脑 IP 后不需要重新编译。只有 MQTT 连接成功后，端点才会连同版本和 CRC 写入 EEPROM；下次启动先尝试已保存端点，同时继续监听新广播并自动切换。

串口输入 `STATUS` 可查看 Wi-Fi、ESP IP、RSSI、MQTT、当前 Broker 与可用堆。STM32 发送一行 `ut.telemetry.v1` JSON 后，固件发布到对应角色的主题：
- **`esp01_ctrl01`** 发布至 `ut/v1/CTRL-01/telemetry`，携带 Node A 本地传感器项；订阅 `ut/v1/CTRL-01/cmd/#` 接收云端与菜单命令。
- **`esp01_ctrl02`** 发布至 `ut/v1/CTRL-02/telemetry`，携带 Node B 本地传感器项；同时订阅 `ut/v1/CTRL-01/telemetry` 接收远端快照供主屏浏览，菜单命令定向发布至 `ut/v1/CTRL-01/cmd/menu`。
两角色均支持包含 `items` 与 `alarmLabel` 的多传感器完整序列化，不丢弃 assetCode。

正常启动时可观察到：

```text
#DISCOVERY listening udp=4210
#DISCOVERY broker=<电脑当前IP>:1884
#MQTT connected
#DISCOVERY broker_saved
```
