# STM32F103RCT6 台架固件

本目录保存综合管廊现场控制器的首个可编译、可烧录台架基线。工程由 STM32CubeMX 生成，使用 STM32CubeF1 HAL、CMake 和 Arm GNU Toolchain。

## 当前已接入

| 模块 | MCU 接口 | 当前状态 |
|---|---|---|
| 1.44 寸 ST7735S TFT | PB4—PB9，软件 SPI | 已完成显示与局部刷新验证 |
| DHT11 | PA1，单总线 | 已完成采集与屏幕显示验证 |
| 水位传感器 | PC0 / ADC1_IN10 | 已完成 ADC 采集和界面接入；干湿阈值待实测校准 |
| SW-420 震动模块 | PA4 / EXTI4 | 已完成双边沿中断和 5 秒报警锁存；实体触发结果待补录 |
| 板载 LED | PA8 | 用于 DHT11 成功读取指示 |
| USART2 遥测 | PA2/PA3，9600 bit/s，8N1 | 每2秒发送一行 `ut.telemetry.v1` JSON；已通过JDY-31实体链路验证，可直接供ESP8266 MQTT桥接收 |

水位报警阈值目前暂设为 `1000`（12 位 ADC 原始值），不得作为最终阈值或真实安全联锁依据。

## 接线表

### TFT（ST7735S）

| TFT | STM32 |
|---|---|
| GND | GND |
| VCC | 3V3 |
| SCL | PB4 |
| SDA | PB5 |
| RES | PB6 |
| DC | PB7 |
| CS | PB8 |
| BLK | PB9 |

### USART2通信

| 设备侧 | STM32 |
|---|---|
| 模块 RXD | PA2 / USART2_TX |
| 模块 TXD | PA3 / USART2_RX |
| GND | GND |

串口配置为 9600 bit/s、8N1。STM32 每2秒发送温湿度、水位和震动告警的行式JSON，行末为 `\r\n`。该协议已通过JDY-31链路完成实体端到端验证；项目负责人确认ESP8266-01S已按相同配置与STM32真机连接，并完成真实采集数据上行至华为云IoTDA。

### 传感器

| 模块 | VCC | GND | 信号 |
|---|---|---|---|
| DHT11 | 3V3 | GND | DATA → PA1 |
| 水位传感器 | 3V3 | GND | S → PC0 |
| SW-420 | 3V3 | GND | DO → PA4 |

## 构建环境

- STM32CubeMX 6.18.1
- STM32Cube FW_F1 V1.8.7
- Arm GNU Toolchain 12.2.1
- CMake 3.22 或更高版本
- Ninja

## 编译

在本目录执行：

```powershell
cmake --preset Debug --fresh
cmake --build --preset Debug
```

构建成功后自动生成：

```text
build/Debug/led_blink.elf
build/Debug/led_blink.bin
```

`CMakeLists.txt` 已配置链接后自动执行 `objcopy`，避免出现 ELF 已更新但 BIN 仍为旧版本的问题。

## 烧录

可使用 ST-Link/SWD 或 STM32 系统串口 BootLoader。串口方式的进入顺序为：

1. `BOOT0=1`、`BOOT1=0`；
2. 复位 MCU；
3. 使用 STM32CubeProgrammer 或兼容工具写入 `build/Debug/led_blink.bin`，起始地址 `0x08000000`；
4. 校验成功后恢复 `BOOT0=0`、`BOOT1=0`，再次复位。

当前 CubeMX 配置为释放调试复用引脚，日常烧录以串口 BootLoader 流程为准。若后续恢复 ST-Link/SWD，应在不占用 TFT 的 PB4 前提下重新核对 SYS 调试配置。

## 当前界面

- `T`：DHT11 温度
- `H`：DHT11 湿度
- `W`：水位 ADC 原始值
- `WATER OK / WATER ALARM`：临时积水状态
- `VIB OK / VIB ALARM`：震动状态，触发后保持约 5 秒

## 待完成

- 记录水位传感器干燥、浅水、目标报警水位的 ADC 值并冻结阈值和回差；
- 实测 SW-420 常态/触发电平、旋钮灵敏度和误触发情况；
- 接入蜂鸣器并实现本地报警联动；
- 归档ESP8266启动日志、Broker消息与IoTDA接收截图；完成断网重连、下行命令和连续运行验收；
- 增加通信状态机、发送确认、失败缓存、故障码和更完整的数据质量处理；
- 将台架代码按驱动、服务、业务状态机和协议层拆分。

## 已验证边界

- `STM32 → JDY-31 → Windows串口网关 → Fastify/PostgreSQL/SSE/React` 已完成实体端到端验证。
- `STM32 → ESP8266 → 本地MQTT → IoTDA` 已完成真实采集数据上行验证；仓库仍需补齐日志、截图、测试时间、断网恢复和连续运行证据。
- 当前串口发送使用阻塞式 `HAL_UART_Transmit`，适合台架；执行器和更多传感器接入后应改为中断/DMA队列，避免长报文阻塞主循环。
