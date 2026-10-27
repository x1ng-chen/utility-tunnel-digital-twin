# 四主控与S3：独立RS-485诊断固件

> 最新扩展（2026-10-26）：1～4号从站镜像和S3四从站轮询环境`quad`已构建；实施步骤见[四板验收清单](FOUR-NODE-ACCEPTANCE.md)。单地址4与3/4双从站的既有实测结果继续作为已验证基线，不代表四从站或四节点业务固件已通过。

**当前状态：4号链路与断线恢复已实测；3号单板启动已实测；S3的3/4双从站和1～4四从站镜像均已构建；1/2号尚未烧录；四从站镜像尚未烧录；完整四板主干尚未确认接完。** 不因诊断地址可配置1～4，就宣称四节点业务固件或总线已验收。

[验收摘要](acceptance-summary.json)包含计数、结论和原日志SHA256；[状态与产物指纹](build-status.json)区分当前源码、已测试旧镜像和未烧录的新镜像。下文`artifacts/`及摘要中的`local-evidence/`均为操作者本地保存位置，原始日志、芯片UID、Flash备份、配置与构建二进制不随源码发布；这些摘要不能替代独立的现场复验。

本目录是短时台架用的临时固件，不替换旧NodeA/NodeB源码，不是四节点生产协议或传感器固件。上电仅使用串口，不启用屏幕、传感器、风机、继电器、蜂鸣器、灯带、Wi-Fi或语音。

## 接线与目标

按[首轮接线表](../../docs/hardware/four-controller-wiring-20261026/bench-01-connection.md)：4号STM32 PA2/TX、PA3/RX；S3 GPIO17/TX、GPIO18/RX；每端独立3.3V模块、共参考地，A对A、B对B。本轮两物理端点接入120Ω，不能把完整总线中4号关闭终端的配置照搬到两节点台架。

S3为主站，只有它主动发起；STM32为地址4的从站，仅对指定合法读请求回复。自动收发485模块无DE/RE控制脚。总线19200、8E1，两个USB日志口均115200、8N1。STM32 HAL使用9位字长加偶校验，等效8位数据加校验，不可误用8位字长加校验而丢掉一个数据位。

STM32诊断时只用内部HSI 8MHz，避免依赖未知外部晶振；UART实际波特率和模块方向切换仍需实测。USART2逐字节中断接收，经有界环形缓冲交主循环，至少4ms总线静默后处理帧。中断不解析协议或写日志。两端均有超时/限长，CRC错误、错误地址和写请求不执行任何输出动作。

## 诊断寄存器

临时约定：Modbus RTU功能03，起始0，数量8；除此之外不回复，不实现生产异常码或写操作。CRC为标准Modbus多项式0xA001、初值0xFFFF、低字节先发。`common/bench_protocol.h`由两端共同使用。

| 寄存器 | 含义 |
| --- | --- |
| 0 | 固定诊断签名0x4853 |
| 1 | 从站编号4 |
| 2 | 诊断协议版本0x0100 |
| 3/4 | 从站本次启动秒数，高/低16位 |
| 5/6 | 合法请求累计次数，高/低16位 |
| 7 | CRC错误累计计数的低16位 |

寄存器不是真实传感器数据，不上传遥测平台。重启后启动秒数与计数复位，不把它们当作UTC或持久序号。S3按配置的间隔读取、等待最多300ms；可忽略本机请求回显，但只有签名、地址、长度、版本和CRC都正确的回复才打印`RS485_OK`。超时/畸形回复打印`RS485_FAIL`及收到的十六进制字节，不伪造成功。

## 轮询模式

S3用编译期位图`BENCH_POLL_MASK`选择从站，bit0～bit3分别对应1～4号：

| 环境 | MASK | 轮询地址 | 单站间隔 |
| --- | ---: | --- | ---: |
| `s3_gateway_bench` | 8 | 4号（单站） | 1000 ms |
| `s3_gateway_bench_dual` | 12 | 4、3号 | 500 ms |
| `s3_gateway_bench_quad` | 15 | 4、3、2、1号 | 500 ms |

扫描顺序固定为4→3→2→1，与主干`GW-01 → 4号 → 3号 → 2号 → 1号`一致。每个从站独立累计polls、successes、timeouts、malformed；某一站超时不影响其他站继续轮询。四站一轮约2秒，日志行带`slave=`和`node_poll=`用于区分。MASK只改变轮询集合，不改变协议、寄存器或从站固件。

## 构建

从仓库根目录执行，使用Arm GNU GCC、CMake、Ninja和HAL/CMSIS：

```powershell
# 从站镜像：把 N 换成 1～4
cmake -S firmware/rs485-bench/stm32 -B firmware/rs485-bench/build/stm32-N -G Ninja -DBENCH_SLAVE_ADDRESS=N
cmake --build firmware/rs485-bench/build/stm32-N
# S3轮询镜像：按单站/双站/四站选择环境
python -X utf8 -m platformio run --project-dir firmware/rs485-bench/s3 -e s3_gateway_bench_quad
```

STM32输出为`build/stm32-N/rs485_ctrl0N_bench.bin`及ELF，链接地址0x08000000、Flash256KB、RAM48KB。S3输出在`s3/.pio/build/<环境名>/`，采用锁定的PlatformIO espressif32 6.13.0与Arduino，按板上N16R8标记暂设16MB Flash、不启用PSRAM。写入前须由esptool实读芯片/Flash确认，不单靠外壳容量标记。不得把S3的应用BIN单独写到0地址；使用PlatformIO的完整上传步骤。

## ST-Link（SWD）与 S3 烧录

本团队用 ST-Link 通过 SWD 下载 STM32；串口 ISP 保留为备选。

**SWD 接线**：`SWDIO → PA13`、`SWCLK → PA14`、`GND → 板GND`。目标板已用 USB 供电时不要再接 ST-Link 的 3.3V，避免双电源。BOOT0/BOOT1 保持 0/0，SWD 不依赖跳帽。

1. 四块板一次接一块 ST-Link；连接后先读芯片 ID（STM32F103RC 为 `0x414`）与 Flash 容量（256 KB），核对板号，不沿用旧 COM 或旧连接。
2. 完整备份原 Flash，记录 SHA256；确认镜像与板号一致（1～4 号对应不同 `BENCH_ADDRESS`）。
3. 写入 `0x08000000` 并校验，例如：

```powershell
STM32_Programmer_CLI -c port=SWD -w build/rs485-1/rs485_ctrl01_bench.bin 0x08000000 -v
```

OpenOCD 等价命令：

```powershell
openocd -f interface/stlink.cfg -f target/stm32f1x.cfg -c "program build/rs485-1/rs485_ctrl01_bench.bin 0x08000000 verify reset exit"
```

4. 烧录会复位目标板；已接在同一条 485 总线上时，其他站短暂超时属正常，烧完再开始正式采集。
5. 用 USART1（PA9/PA10，115200 8N1）看启动日志；ST-Link 不提供业务日志。

**串口 ISP 备选**：BOOT0=1、BOOT1=0，按 RST 进入 ISP，用本次枚举的 COM 口写 `0x08000000`；完成后恢复 BOOT0=0、BOOT1=0 再复位。不要把示例 COM 当作实际端口。

**S3**：无 STM32 式 BOOT 跳帽。正常 USB 串口下载可自动进下载模式；仅在握手失败且目标已确认时，按住 BOOT、点 RST 后松 BOOT。不要先擦除整片 Flash 或更改 eFuse。旧镜像先按实际 Flash 容量备份，再通过本次确认的 UART 口上传并检查校验结果。烧录期间设备复位不等于总线故障。

## 验证与恢复

运行后读取S3日志，观察连续`RS485_OK`、从站requests递增与uptime推进；STM32日志有启动标识`RS485_BENCH_V1 CTRL-04`及CRC/UART/环形缓冲错误计数。USB枚举、LED亮或写入校验通过都不能代替总线通信证据。

首验建议记录至少30次查询的原始日志和成功/失败次数；由用户断电操作模拟断线后，重新接入并确认新请求恢复。几十秒通过只代表短时台架，未覆盖四从站竞争、长稳、全机负载或业务控制。

本镜像没有业务功能。恢复时使用已保存、已核对目标的旧Flash备份；不能将旧两节点镜像接在共享485上当作四节点固件运行。完整四节点固件需另行接入新编号、传感器清单、菜单及受控下行协议。

目前状态与产物指纹见[build-status.json](build-status.json)；任何未执行的硬件步骤保留未执行状态。

2026-10-26本轮结果：两端固件均构建成功。用户确认COM5仅接4号STM32后，实读芯片ID0x414、Flash256KB，完整备份旧Flash；最终8996字节镜像写入、工具校验和独立读回SHA256均一致。初次ROM跳转未取得日志，补充应用向量表定位及中断初始化后，最终镜像在真机输出两次`selftest=PASS`、uptime5006/10014ms，UART/CRC/缓冲溢出计数为0。此时requests=0，S3尚未烧录，没有485通信通过结论。接下来恢复BOOT0/BOOT1为0并物理复位，再接S3 UART口识别和备份/烧录。

同日后续：S3接COM口后枚举为COM3/CH343，实读ESP32-S3 rev0.2、16MB Quad 3.3V Flash及8MB PSRAM。完整16MB备份后，通过PlatformIO写入四段镜像且均通过工具哈希校验；另读回0x00000000～0x00050FFF，逐段比较bootloader、分区、boot_app0和应用字节全部一致。首次35秒采集到35条连续合法回复，poll7～41、从站requests7～41，CRC为0，无失败；S3读回后自动RTS复位，再采集12条合法回复，通信自动恢复。结果见`artifacts/rs485-bench-20261026/rs485-acceptance.json`。

UART累计错误在首次诊断轮询前已有674次，S3读回/复位窗口后为675次，两段正常采集期间均未继续增加；不能宣称累计UART错误为0，过渡窗口原因仍需专项测试。当前通过的是两端短时读请求/回复和S3复位后恢复，不包含实体拔线恢复、STM32冷启动、四节点、负载并行或长期稳定性。

同日再执行实体A/B断开与接回：用户保持GND、USB与RST不变，日志共采集200轮；主中断区间poll460～489连续30次无接收超时，poll490～535连续46次合法回复，接回后自行恢复。网关poll计数连续、STM32 uptime递增，请求计数在519暂停后继续，无观察到的重启；本轮CRC/溢出为0，UART累计675未增长。报告为`artifacts/rs485-bench-20261026/disconnect-01-acceptance.json`。

另在主中断区间之前poll364出现一次独立超时，其原因未定位，不能把本次写作零丢包或全部超时都由人为断线造成。冷启动、四节点、负载和长期稳定性仍未验收。`monitor.py`支持最长600秒的有界采集及`--stop-file`标记提前正常退出；日志读取时不主动切换DTR/RTS。
