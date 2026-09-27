# STM32F103RCT6 双节点台架固件

当前活动固件是两块 STM32F103RCT6 通过两块 ESP8266-01S 及 MQTT 通信的 Node A / Node B 组合。两块板都运行 72 MHz 外部晶振时钟，各带一块 1.44 寸 ST7735S 屏。**不要烧录旧的 DHT11 `bench` 映像。**

`CTRL-01` / Node A 是采集、执行与安全联动节点，屏幕为**只读自动轮播副屏**；
`CTRL-02` / Node B 是唯一交互主屏，由**五针模拟摇杆**控制菜单并下发命令。

> 引脚权威约定见 `docs/hardware/双屏与摇杆接线.md`；
> 实物验收流程与当前待办见 `docs/acceptance/双屏菜单实机验收.md`。
> 本文只描述固件的构建与行为边界，**不代表实物已接线或已验收**。

## 当前节点与角色

| 节点 | 角色 | 屏幕 | 摇杆 | 通信 |
|---|---|---|---|---|
| `CTRL-01` / Node A | 采集、执行器、安全联动、回执 | SPI3 只读副屏，5 s 轮播，报警接管 | 不接 | ESP-01 `esp01_ctrl01`，USART2 9600 8N1 |
| `CTRL-02` / Node B | 菜单交互、命令下发、主屏显示 | SPI1 交互主屏，60 FPS 菜单 | 五针模拟摇杆 | ESP-02 `esp01_ctrl02`，USART2 9600 8N1 |

Node A 的副屏**不接受摇杆输入、不解析 MQTT、不驱动执行器**；Node B 的命令
只有在收到携带相同 `cmdId` 的 `ut.command.ack.v1` 回执后才算执行成功。

## 引脚速查

### 屏幕

| 信号 | Node A | Node B |
|---|---|---|
| `SCL` | `PB3 / SPI3_SCK` | `PA5 / SPI1_SCK` |
| `SDA` | `PB5 / SPI3_MOSI` | `PA7 / SPI1_MOSI` |
| `RES` | `PC4` | `PB6` |
| `DC` | `PC5` | `PB7` |
| `CS` | **`PC6`** | `PB8` |
| `BLK` | **`PC7`** | `PB9` |

Node A 的 `CS/BLK` 是 `PC6/PC7`：`PB8/PB9` 在 Node A 上是 `TIM4_CH3/CH4`
两路 25 kHz 风机 PWM，**不可占用**。Node B 无此冲突，沿用开发板 LCD 排针
原有控制线。`PA6` 在 Node B 不连接。

两节点**共用**的 `HAL_MspInit()`（`Core/Src/stm32f1xx_hal_msp.c`）**无条件**
执行 `__HAL_AFIO_REMAP_SWJ_NOJTAG()`：**两块板都关闭 JTAG、都保留 SWD 于
`PA13/PA14`**。Node A 借此释放 `PB3` 作 SPI3_SCK；Node B 的 `PA15/PB3/PB4`
也因此释放但当前未使用。SWD 与串口 BootLoader 烧录路径不受影响。

### 摇杆（仅 Node B）

| 摇杆 | Node B | 说明 |
|---|---|---|
| `GND` | `GND` | 共地 |
| `+5V`（丝印） | **`3.3V`** | **必须接 3.3 V**；`VRx/VRy` 直接进 ADC |
| `VRx` | `PC0 / ADC1_IN10` | 水平 |
| `VRy` | `PC1 / ADC1_IN11` | 垂直 |
| `SW` | `PC4` | 内部上拉，按下为低 |

> ⚠️ 摇杆模块丝印写 `+5V`，但**只能接 3.3 V**。接 5 V 会让推到底时的
> ADC 输入接近 5 V，超过 STM32 绝对最大额定值，可能永久损坏 `PC0/PC1`。

### ESP8266 与调试串口（两节点相同）

| STM32 | 连接 | 参数 |
|---|---|---|
| `PA2 / USART2_TX`、`PA3 / USART2_RX` | ESP-01S | 9600 8N1，72 MHz 下 BRR=3750，误差 0 |
| `PA9 / USART1_TX`、`PA10 / USART1_RX` | 调试/烧录串口 | 9600 8N1，BRR=7500，误差 0 |

ESP-01S 必须独立稳定 3.3 V 供电，不得接 5 V。烧录模式见
`firmware/esp8266-01s/README.md`。

### Node A 现有接线（本次改造全部保留）

| 功能 | 引脚 |
|---|---|
| SHT30 软件 I²C 总线 1 / 总线 2 | `PB6=SCL`、`PB7=SDA` / `PB10`、`PB11` |
| 氧气 / 甲烷 / CO ADC | `PC3 / ADC1_IN13`、`PC2 / ADC1_IN12`、`PC1 / ADC1_IN11` |
| 烟雾数字量 | `PB12`（低电平触发；4 次 50 ms 稳定采样后才报警，无保持时间） |
| 火焰数字量 | `PB14`（低电平触发；立即报警，告警保持 12 s） |
| 液位 L01 | `PC0` |
| 风机 1 / 2 TACH | `PA6` / `PA7`（每转 2 脉冲） |
| 风机 1 / 2 PWM | `PB8 / TIM4_CH3`、`PB9 / TIM4_CH4`（25 kHz） |
| 继电器总使能 / 蜂鸣器 | `PA1` / `PB0` |
| WS2812 灯带 DIN | `PB15 / SPI2_MOSI`（4.5 MHz 编码，18颗） |

新屏幕引脚与上述集合互不相交；契约测试断言 22 个引脚无冲突、`PB8/PB9`
未被屏幕适配器触碰。**基线芯片以 72 MHz 运行；`PCLK1 = 36 MHz`、
`PCLK2 = 72 MHz`、ADC 时钟 `PCLK2/6 = 12 MHz`、FLASH 等待周期 2。**

## 构建

依赖：STM32CubeMX 6.18.1、STM32Cube FW_F1 V1.8.7、Arm GNU Toolchain 12.2.1、CMake 3.22+、Ninja。

### CTRL-01 / Node A（副屏）

```powershell
cmake --preset NodeA --fresh
cmake --build --preset NodeA
```

烧录文件：`build/NodeA/stm32_controller.bin`
当前 Node A 构建占用：RAM 13272 B / 48 KB（27.00%）、FLASH 69716 B / 256 KB（26.59%）。

Node A 的 128×128 副屏每 5 秒轮播八页，汇总两块板的传感器：`ENV` 显示 SHT-01～04；`CO` 显示 CO-01～05；`MQ4` 显示 MQ4-01～05；`O2` 显示 O2-01～03；`MQ2` 显示 MQ2-01～05；`FLAME` 显示 FLAME-01～05；`LEVEL` 显示 L01～L05（L05 已拆除，显示 `PLAN`）；`FAN` 显示两路 PWM、转速及 INA226 电压/电流。Node A 每 2 秒发送一帧既有控制器遥测及一帧轮转的 20 路传感器库存遥测，共用连续序号；Node B 每 2 秒发送一帧轮转的本地传感器遥测。Node B 遥测通过 MQTT 到新版 ESP-01，再以紧凑串口帧送 Node A；超过 30 秒未收到某一路数据或 Node B 离线时，该路显示 `OFF`。**旧版 ESP-01 未实现这条 Node B 回传路径，单独更新 STM32 不会使 Node A 屏幕显示 Node B 的实时值。**报警仍立即接管屏幕。未启用、离线、异常分别显示 `PLAN`、`OFF`、`BAD`；模拟量未经标定，仅显示 `RAW` ADC 计数，数字量显示引脚 `LOW/HIGH`。

### CTRL-02 / Node B（主屏 + 摇杆）

```powershell
cmake --preset NodeB --fresh
cmake --build --preset NodeB
```

烧录文件：`build/NodeB/stm32_controller.bin`
参考占用：RAM 5072 B / 48 KB（10.32%）、FLASH 68744 B / 256 KB（26.22%）。

`Debug` 与 `Release` 也默认构建 Node A。CMake 会在每次成功链接后生成同目录的 `.bin` 文件。

## 主机测试

在 `firmware/stm32f103rct6/` 下运行（需要 `sh` 与主机 `gcc`；Windows 上可用 WSL）：

```powershell
sh tests/run_node_a_status_host.sh      # 副屏页面模型 + SPI3/DMA2 适配器 + 引脚契约
sh tests/run_display_host.sh            # 光栅/总线/时钟/运行/串口探针校验
sh tests/run_ui_renderer_host.sh        # UiRenderer 与菜单适配器
sh tests/run_task8_host.sh              # 快照解析、陈旧判断、时钟保持
sh tests/run_node_a_command_host.sh     # Node A 命令分发与回执
sh tests/run_node_a_telemetry_host.sh   # 遥测帧字节与已提交向量一致
sh tests/run_node_a_telemetry_throughput_host.sh  # 轮转调度与 9600 链路预算（多周期）
sh tests/run_node_a_command_probe_host.sh         # 串口探针的遥测校验器
sh tests/run_node_a_clock_host.sh       # 72 MHz 时钟/外设时序契约
ARM_GCC=arm-none-eabi-gcc.exe sh tests/run_node_a_contract_arm.sh
```

ESP 侧（在 `firmware/esp8266-01s/` 下）：

```powershell
python -m platformio run -e esp01_ctrl01
python -m platformio run -e esp01_ctrl02
python -m platformio test -e native      # 需要主机 gcc/g++，本机缺失
```

## 串口诊断探针

两块板都通过 `USART1`（9600 8N1）接受行式探针，便于无屏幕时核对状态。

| 探针 | 节点 | 用途 |
|---|---|---|
| `#NODETEST DISPLAY` | Node A | 页面、渲染/翻页计数、报警状态、时钟同步与序号、总线统计 |
| `#NODETEST CLOCK` | Node A | 时钟寄存器回读与重算频率 |
| `#NODETEST TELEMETRY` / `STATE` | Node A | 遥测帧与本地状态 |
| `#NODETEST SAFETY <...>` | Node A | 注入报警**输入**（不伪造执行器） |
| `#NODETEST CMD <json>` | Node A | 走同一命令分发路径 |
| `#DISPLAYTEST` / `#DISPLAYTEST RUN` | Node B | 总线与帧统计 |
| `#UITEST ...` | Node B | 菜单状态机（`RESET`/`GOTO`/`TICK`/`UP`/`DOWN`/…） |
| `#JOYTEST x y sw ms` | Node B | 合成 ADC 输入，验证解码与迟滞 |

## 命令链路与主题

```text
Node B 摇杆 → 菜单命令 → USART2 → ESP-02
  → ut/v1/CTRL-01/cmd/menu
  → ESP-01（归一化为 ut.command.v1，保留 cmdId/target/action/value/TTL）
  → USART2 → Node A 执行
  → ut.command.ack.v1（相同 cmdId）→ ESP-01 → ut/v1/CTRL-01/cmd_ack
  → ESP-02 → USART2 → Node B 显示"已执行"
```

| 角色 | 订阅 | 发布 |
|---|---|---|
| ESP-01 `CTRL-01` | `ut/v1/CTRL-01/cmd/#`（已覆盖 `cmd/menu`，不重复订阅） | `ut/v1/CTRL-01/telemetry`、`ut/v1/CTRL-01/cmd_ack`、`ut/v1/CTRL-01/status` |
| ESP-02 `CTRL-02` | `ut/v1/CTRL-01/telemetry`、`ut/v1/CTRL-01/cmd_ack`、`ut/v1/CTRL-01/status` | `ut/v1/CTRL-01/cmd/menu`、`ut/v1/CTRL-02/telemetry`、`ut/v1/CTRL-02/status`；Node B 本地传感器遥测发布到 CTRL-02 主题 |

安全联动优先级始终高于菜单命令：已验证的甲烷报警可强制通风、红色闪烁和
蜂鸣；未标定的氧气与 CO 通道只显示数据，不驱动执行器。5 秒内没有匹配回执
显示超时，迟到回执只更新设备实际状态，**不会**把已超时的确认框改成成功。

## 安全与凭据

- 两块 STM32 与两块 ESP8266 **都不保存华为云设备密钥，也不直接连接 IoTDA**；
  云端凭据只在网关侧注入。
- Wi-Fi 口令与 MQTT 凭据只写入 `firmware/esp8266-01s/include/secrets.h`
  （已 gitignore），不得出现在仓库、串口日志或文档中。
- 台架 MQTT 只允许在隔离局域网使用明文；不得把匿名 Broker 暴露到公网。
- 气体异常只在隔离信号模拟盒上注入；**不在教室释放可燃或有毒气体**。

## 串口 BootLoader 烧录

1. `BOOT0=1`、`BOOT1=0`，复位 MCU；
2. 使用 STM32CubeProgrammer 或兼容工具写入相应的 `.bin`，起始地址 `0x08000000`；
3. 校验成功后恢复 `BOOT0=0`、`BOOT1=0`，再次复位。

SWD（`PA13/PA14`）在两块板上都保留，可随时用 ST-Link 连接；两块板共享的
`HAL_MspInit()` 都关闭 JTAG，这同样不影响 SWD 调试与烧录。

## 旧 bench 说明

`Core/Src/main.c`、DHT11（PA1）、PC0 水位 ADC 和 SW-420（PA4）是早期单板台架程序的历史记录。它们仍可通过显式 `FIRMWARE_VARIANT=bench` 供回归使用，但不是当前控制器默认映像，不能作为 SHT30 双节点系统的接线或烧录依据。


## 双节点 32 路多传感器扩展架构

固件已全面扩展支持双节点 32 路物理传感器拓扑（Node A 20 路，Node B 12 路）：

- **SHT30 温湿度**：4 路（Node A 两条独立软件 I2C 总线，每条总线支持 0x44/0x45 双地址）
- **模拟量输入**：13 路（Node A 7 路：3 路已有 PC1-PC3 + 4 路新增 PA0, PA4, PA5, PB1；Node B 6 路：PA0, PA1, PA4, PA6, PB0, PB1）
- **数字量输入**：15 路（Node A 9 路：PB12、PB13、PB14、PC0、PC8、PC9、PC11、PC12、PC13；Node B 6 路：PC6-PC11）。Node A 的 PC10 已由风机 01 基极接线占用，不分给 MQ2-02。
- **安全与隔离策略**：
  - 当前台架已接的 31 路默认启用采集；已拆除的 `LEVEL-05` 保持禁用。启用采集不等于校准或授权报警联动；
  - 仅显式标定且受权通道（`MQ4-01` 等）触发自动通风与声光联锁；
  - 模拟未标定通道上报 `suspect`，数字通道实施 4 次去抖滤波；
  - 各传感器独立陈旧超时，单点断线不影响同总线或其余 31 路通道。
- **文档与接线指引**：
  - 完整接线预检清单：`docs/hardware/dual-node-sensor-wiring-checklist.md`
  - 实机调试记录模板：`docs/hardware/dual-node-sensor-commissioning-log.md`

## 尚未完成的实体验收

以下项目**全部未完成**，构建通过不代表已经验收：

- 两块屏幕与摇杆的实物接线连续性、摇杆 3.3 V 供电实测；
- Node A / Node B 实际烧录与 COM 口探针输出；
- **实测** SPI 频率、全屏刷新耗时、菜单帧率与最终稳定分频；
- 甲烷/烟雾/火焰报警注入与双屏一致性、断网本地联动；
- 两台风机的独立/联动命令、灯带与蜂鸣器逐项实机核对；
- 连续运行 30 分钟无花屏、无丢帧、无死机。

详细清单见 `docs/acceptance/双屏菜单实机验收.md`。
