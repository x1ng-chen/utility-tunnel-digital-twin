# 硬件工程工件

> **当前台架版本（2026-09-28）**：Node A/B 与双 ESP 已接入 31 路传感器，项目负责人已确认当前范围验收。可烧录源码、当前引脚表及全传感器记录位于 [功能分支](https://github.com/x1ng-chen/utility-tunnel-digital-twin/tree/feature/dual-screen-joystick-menu)，接线以 [9 月 27 日冻结表](https://github.com/x1ng-chen/utility-tunnel-digital-twin/blob/feature/dual-screen-joystick-menu/docs/hardware/2026-09-27-双节点台架外部传感器接线冻结.md)为准。下文保留 main 的早期接口/构建说明，不应当作当前台架完整接线或烧录指令。详见 [当前状态](../docs/项目当前状态.md)。

本目录用于保存可制造、可验收的硬件交付物，避免以模型、库存登记或固件编译结果代替实体证据。

## 早期基线（历史参考）

- 当前控制器：STM32F103RCT6 开发板。
- 当前无线链路：ESP8266-01S，USART2（PA2/PA3，9600 bit/s）连接。
- 当前活动双节点链路：Node A 读取 SHT30（当前已接入 Slot 1），经 ESP8266 `CTRL-01` 发布；Node B 经 ESP8266 `CTRL-02` 接收并显示在 ST7735S TFT。该链路已完成台架通信验证。
- DHT11、PC0 水位 ADC 与 SW-420 属于早期单板 `bench` 演示，保留作历史参考，不是当前控制器的默认烧录映像。
- 当前风机：冰域（BINGDU）B12，铭牌为 DC 12 V / 0.20 A。四根线的功能已确认分别为负极、正极、TACH 转速反馈、PWM 调速；线色与插头针序、PWM 电平/频率、TACH 每转脉冲数仍待现场核验。

## Carrier32 当前状态

32 路接口板仅有设计/展示草稿，布线、电气/机械复核和制造发布尚未放行；31 路实物展示验收不代表 PCB 可制造。当前资料在功能分支的 `hardware/carrier32/`。

## 目录约定

- `bench/`：台架接线、实物核验、验收记录和照片索引。
- `schematic/`：经评审的原理图源文件与 PDF。
- `pcb/`：PCB 源文件、ERC/DRC 报告、Gerber 与装配资料。
- `bom/`：可下单 BOM、替代料与到货状态。

只有在 `bench/` 的核验项通过、嵌入式引脚表冻结且安全默认态已验证后，才能创建最终 PCB 设计。

## 当前禁止项

- 不把 24 V 水泵接入当前 MVP。
- 未提供数据手册的 DCP-3620 不进入原理图或 MCU 引脚分配。
- 不在教室释放可燃或有毒气体；气体异常仅使用隔离信号模拟。
