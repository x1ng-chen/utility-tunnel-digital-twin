# STM32F103RCT6 双节点台架固件

> **当前台架版本（2026-09-28）**：Node A/B 与双 ESP 已接入 31 路传感器，项目负责人已确认当前范围验收。可烧录源码、当前引脚表及全传感器记录位于 [功能分支](https://github.com/x1ng-chen/utility-tunnel-digital-twin/tree/feature/dual-screen-joystick-menu)，接线以 [9 月 27 日冻结表](https://github.com/x1ng-chen/utility-tunnel-digital-twin/blob/feature/dual-screen-joystick-menu/docs/hardware/2026-09-27-双节点台架外部传感器接线冻结.md)为准。下文保留 main 的早期接口/构建说明，不应当作当前台架完整接线或烧录指令。详见 [当前状态](../../docs/项目当前状态.md)。

当前活动固件是两块 STM32F103RCT6 通过两块 ESP8266-01S 及 MQTT 通信的 Node A / Node B 组合。**不要烧录旧的 DHT11 `bench` 映像。**

## 早期双节点接口（历史参考）

| 节点 | 作用 | 已验证接口 |
|---|---|---|
| `CTRL-01` / Node A | 采集并发布环境数据 | SHT30 Slot 1：PB6=SCL、PB7=SDA、3.3 V、I²C 地址 `0x44`；ESP8266：PA2→RX、PA3←TX，9600 8N1 |
| `CTRL-02` / Node B | 接收 Node A 数据并显示 | ESP8266：PA2→RX、PA3←TX，9600 8N1；ST7735S TFT：PB4=SCL、PB5=SDA、PB6=RES、PB7=DC、PB8=CS、PB9=BLK |

所有模块必须共地；ESP8266 使用稳定独立的 3.3 V 供电。Node A 发布 SHT30 数据后，MQTT 转发服务将 Slot 1 数据转发到 Node B；台架已观察到 Node B TFT 显示来自 Node A 的温湿度。

## 构建

依赖：STM32CubeMX 6.18.1、STM32Cube FW_F1 V1.8.7、Arm GNU Toolchain 12.2.1、CMake 3.22+、Ninja。

### CTRL-01 / Node A（本分支早期构建）

```powershell
cmake --preset NodeA --fresh
cmake --build --preset NodeA
```

烧录文件：

```text
build/NodeA/stm32_controller.bin
```

### CTRL-02 / Node B（TFT 显示）

```powershell
cmake --preset NodeB --fresh
cmake --build --preset NodeB
```

烧录文件：

```text
build/NodeB/stm32_controller.bin
```

`Debug` 与 `Release` 也默认构建 Node A。CMake 会在每次成功链接后生成同目录的 `.bin` 文件。

## 串口 BootLoader 烧录

1. `BOOT0=1`、`BOOT1=0`，复位 MCU；
2. 使用 STM32CubeProgrammer 或兼容工具写入相应的 `.bin`，起始地址 `0x08000000`；
3. 校验成功后恢复 `BOOT0=0`、`BOOT1=0`，再次复位。

## 旧 bench 说明

`Core/Src/main.c`、DHT11（PA1）、PC0 水位 ADC 和 SW-420（PA4）是早期单板台架程序的历史记录。它们仍可通过显式 `FIRMWARE_VARIANT=bench` 供回归使用，但不是当前控制器默认映像，不能作为 SHT30 双节点系统的接线或烧录依据。

## 尚未完成的实体验收

- 接入其余 SHT30 通道，并完成同地址传感器的 I²C 复用/地址规划；
- MQTT 下行命令 → STM32 → 执行器 → 执行回执的真实闭环；
- 水位、气体与执行器的供电、电平调理、标定和安全验证。
