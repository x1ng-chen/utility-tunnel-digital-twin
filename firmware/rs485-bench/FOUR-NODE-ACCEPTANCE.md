# 四板 RS-485 总线：烧录与验收清单

2026-10-26。适用：V0.3 就近接线（1 左下、2 右下、3 右上、4 左上）＋本目录诊断固件。

> **边界**：这是短时台架诊断固件，只读 8 个诊断寄存器，不采集传感器、不控制执行器、不上报平台。四板总线通过只证明物理链路和 Modbus 协议连通，**不等于四节点业务固件或整机验收**。

## 1. 前置检查（断电）

| 项目 | 要求 |
| --- | --- |
| 板号 | 按板上实际标签：1 左下、2 右下、3 右上、4 左上 |
| 485 模块 | 5 个：GW-01＋四块 STM32 各一 |
| 主干 | `GW-01 → 4号 → 3号 → 2号 → 1号`，不星型、不闭环 |
| 接线 | A 接 A、B 接 B，同一对双绞线；四板与网关共参考地 |
| 终端电阻 | **GW-01 和 1号 SW1 = ON**；4/3/2 号 = OFF |
| 供电 | 每块板 3.3V 给本板 485 模块；模块不接 5V |
| 串口 | STM32 用 ISP 口，S3 用 UART Type-C；同时只接一路调试电源时注意共用供电 |

断电用万用表核对：

- A/A、B/B、GND 三线对应，无错位。
- 两端终端都 ON 时，断开所有设备测量 A–B 约 **60Ω**（两个 120Ω 并联）；中间站 SW1 必须断开。
- 每板 PA2 → 模块 TXD、PA3 ← 模块 RXD；NC 悬空。

**排错提示**：若上电后四个从站全部超时，先怀疑 A/B 名字与实物相反。断电交换 A/B 后再试，不要带电插拔。

## 2. 镜像与烧录

本轮用 GCC 14.2.1 重新构建，镜像字节数和 SHA256 与此前记录不同，**不要拿旧哈希核对新文件**。

| 目标 | 构建环境 | 文件 | 字节 | SHA256（前 8 位） | 当前状态 |
| --- | --- | --- | ---: | --- | --- |
| 1号 | `-DBENCH_SLAVE_ADDRESS=1` | `build/rs485-1/rs485_ctrl01_bench.bin` | 8960 | `be073195` | 待烧录 |
| 2号 | `-DBENCH_SLAVE_ADDRESS=2` | `build/rs485-2/rs485_ctrl02_bench.bin` | 8964 | `80c7208c` | 待烧录 |
| 3号 | `-DBENCH_SLAVE_ADDRESS=3` | `build/rs485-3/rs485_ctrl03_bench.bin` | 8960 | `232e96d8` | 已烧旧镜像，可不重烧 |
| 4号 | `-DBENCH_SLAVE_ADDRESS=4` | `build/rs485-4/rs485_ctrl04_bench.bin` | 8960 | `b7c11dde` | 已烧旧镜像，可不重烧 |
| S3 | `-e s3_gateway_bench_quad` | `s3/.pio/build/s3_gateway_bench_quad/firmware.bin` | 265872 | `98814e05` | 待烧录 |

3/4 号现有镜像是此前编译器构建的，协议与寄存器一致，可以继续使用；若要四块完全一致，再重烧，但需重新记录哈希。

### STM32 烧录（ST-Link / SWD，每块）

**接线**：ST-Link 的 `SWDIO → PA13`、`SWCLK → PA14`、`GND → 板 GND`。目标板已用 USB 供电时**不要再接 ST-Link 的 3.3V**，避免双电源；目标板单独供电时才接 3.3V。

**BOOT0 / BOOT1 保持 0 / 0**，SWD 不依赖跳帽，也不需要按复位进下载模式。

1. 连接后先读芯片 ID（STM32F103RC 为 `0x414`）和 Flash 容量（256 KB），核对本次接的是哪一块板；四块板一次接一块 ST-Link。
2. 完整备份原 Flash，记录 SHA256；确认镜像与板号一致（1～4 号对应不同 `BENCH_ADDRESS`）。
3. 写入 `0x08000000` 并校验。STM32CubeProgrammer CLI：

```powershell
STM32_Programmer_CLI -c port=SWD -w build/rs485-1/rs485_ctrl01_bench.bin 0x08000000 -v
```

OpenOCD 等价命令：

```powershell
openocd -f interface/stlink.cfg -f target/stm32f1x.cfg -c "program build/rs485-1/rs485_ctrl01_bench.bin 0x08000000 verify reset exit"
```

4. 烧录会复位目标板。四块板已接同一条 485 总线时，烧录某一块会短暂打断总线，其他站出现超时属正常；烧完再开始正式验收采集。
5. 用 USART1（PA9/PA10，115200 8N1）看启动日志；ST-Link 不提供业务日志。

**串口 ISP 备选**：BOOT0=1、BOOT1=0，按 RST，用本次枚举的 COM 口写 `0x08000000`，完成后恢复 BOOT0=0、BOOT1=0 再复位。不要把示例 COM 当作实际端口。

启动日志应看到：

```text
RS485_BENCH_V1 CTRL-0N SLAVE=N BUS=PA2/PA3 19200-8E1 DIAGNOSTIC_ONLY
CTRL0N_BENCH selftest=PASS uptime_ms=... requests=0 crc_errors=0 uart_errors=... overruns=0
```

### S3 烧录

1. 接 UART Type-C，确认枚举口。
2. 完整备份原 Flash，记录 SHA256。
3. 从仓库根目录执行：

```powershell
python -X utf8 -m platformio run --project-dir firmware/rs485-bench/s3 -e s3_gateway_bench_quad -t upload
```

4. 115200 串口应看到：

```text
RS485_BENCH_V1 S3_MASTER TX=17 RX=18 19200-8E1 MASK=15 DIAGNOSTIC_ONLY
PROTOCOL_SELFTEST PASS cases=9
```

`MASK=15` 表示轮询 1～4 号全部从站。

## 3. 分阶段验收

每阶段单独保存原始日志，命名带板号、日期、端口。

### A. 单站基线（已完成，可跳过）

只接 4 号＋GW，S3 用 `s3_gateway_bench`。至少 30 次 `RS485_OK`。

### B. 双站

接 4、3 号，S3 用 `s3_gateway_bench_dual`。

- 两个 `slave=` 各自递增，`RS485_FAIL` 为 0。
- 拔掉 3 号 A/B：4 号继续 OK，3 号出现 timeout；接回后 3 号恢复。

### C. 四站

接 4、3、2、1 号，S3 用 `s3_gateway_bench_quad`。

- 每站至少 **30 次连续 `RS485_OK`**。
- 四站一轮约 2 秒，日志中 `slave=1/2/3/4` 都出现且 `node_poll` 递增。
- 全程 `crc_errors=0`、`overruns=0`，`RS485_FAIL` 不出现。
- 各从站 `requests` 与 S3 的 `node_poll` 应同步增长。

### D. 故障与恢复

| 用例 | 操作 | 通过标准 |
| --- | --- | --- |
| 单站断线 | 拔 2 号 A/B，保持 GND 和供电 | 其他三站继续 OK；2 号 timeout 增长；接回 ≤5 秒恢复 |
| S3 复位 | 按 S3 RST | 复位后自动恢复轮询，不要求重新上电从站 |
| 从站冷启动 | 断电重启任一块 STM32 | 重新上线后该站恢复 OK，其他站不受影响 |
| 终端误配（可选） | 把中间某站 SW1 打开 | 记录现象后恢复正确配置，不得作为通过项 |
| 长稳 | 连续采集 10 分钟（`monitor.py --seconds 600`，可分段） | 无新增 CRC/溢出；各站成功率 >99% |

### E. 负载并行（可选，进入整机前）

接入风机、继电器、屏幕，由各自固件或手动触发，观察 485 是否出现新增 CRC/超时。诊断固件本身不驱动这些负载。

## 4. 记录模板

```text
日期/时间：
板号与端口：
镜像 SHA256：
S3 环境（single/dual/quad）：
采集时长：
每站：成功 / 超时 / 畸形
CRC 错误：       溢出：
断线与恢复：是否通过，恢复耗时
异常现象与原始日志路径：
```

## 5. 通过标准（四站总线）

1. 1～4 号各自 ≥30 次连续合法回复。
2. 任意单站断线不影响其他站；接回 ≤5 秒恢复。
3. CRC 错误、环形缓冲溢出为 0。
4. S3 复位后自动恢复。
5. 至少一个从站冷启动后能重新上线。
6. 原始日志、镜像、备份和哈希已保存。

任一项未完成，状态写「未验收」，不写「通过」。

## 6. 回退

1. STM32：用第 2 步保存的原 Flash 备份写回，恢复 BOOT0/BOOT1=0。
2. S3：用备份的 16 MB Flash 镜像恢复；或重新烧录旧环境的 `s3_gateway_bench`。
3. 不得把旧两节点业务镜像接到四节点共享 485 上运行。

## 7. 已知未决

- 早期单站测试出现过一次独立超时（poll364），原因未定位。
- UART 累计错误计数在诊断前已有 674 次，S3 读回窗口后为 675，正常采集期间未增长；来源未查清。
- 四从站、冷启动、长稳、整机负载均尚未执行。
