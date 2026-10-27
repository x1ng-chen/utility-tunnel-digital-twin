# 四主控接线与源码对照 V0.4

2026-10-27。模型为700×700×300 mm；位置为左下1、右下2、右上3、左上4。此版将10月26日规划与现行四节点源码对齐，不代表已按本表完成实物接线、烧录或电气验收。

**证据边界：31路身份和空间归属保持不变，修订实际源码使用的引脚；历史10月24日方案、原两节点固件、V16/V17模型及10月26日台架记录保留。**

## 分区与设备归属

```text
        GW-01（左上干区）
        │
   4号/P1 ─────────── 3号/P2
   风机1              蜂鸣器、18颗灯带
                           │
            P5             │
             ╲             │
   1号/P3 ─────────── 2号/P4
   状态屏、P5线束      主屏、摇杆、风机2
```

横竖线表示RS-485主干，P5斜线表示独立传感器线束；A/B不闭环。管廊展示管道与通风排气是两套用途，风机用于排气。局部ADC/DO/I²C不跨区连接。

| 主控 | 位置 | 检测站 | 物理传感器数 | 其他本地设备 |
| --- | --- | --- | ---: | --- |
| CTRL-01 | 左下 | P3＋P5 | 11 | 状态屏 |
| CTRL-02 | 右下 | P4 | 7 | 主屏、摇杆、FAN-02、RELAY-02、INA226-FAN2 |
| CTRL-03 | 右上 | P2 | 6 | 蜂鸣器、灯带 |
| CTRL-04 | 左上 | P1 | 7 | FAN-01、RELAY-01、INA226-FAN1 |

31路＝MQ-2/MQ-4/MQ-7（CO）各5＋火焰5＋温湿度4＋液位4＋氧气3。温湿度的两个指标只计一个物理模块；两路INA226另计执行器反馈。P1～P5、实物尾号和三维定位对象保持一致。新主控编号不会自动重写历史数据或V17中的旧文字标签。

## 相对V0.3的引脚修订

| 设备 | V0.3引脚 | 当前源码引脚 |
| --- | --- | --- |
| MQ2-03 / CTRL-01 | PC11 | PC4 |
| MQ4-03 / CTRL-01 | PC2 | PA4 |
| CO-03 / CTRL-01 | PB1 | PA5 |
| MQ2-05 / CTRL-01 | PB13 | PC5 |
| MQ4-05 / CTRL-01 | PA4 | PA6 |
| CO-05 / CTRL-01 | PC1 | PA7 |
| LEVEL-03 / CTRL-01 | PC13 | PB1 |
| O2-02 / CTRL-01 | PA5 | PA0 |
| 两屏CS/BLK | PB9 / PC12 | PB8 / PB9 |
| FAN-02 PWM / CTRL-02 | PB8 / TIM4_CH3 | PB1 / TIM3_CH4 |

**PA0例外没有消除：** 1号O2-02按上传源码使用PA0/ADC1_IN0，而库存板资料曾将PA0列为WKUP按键。须核对该板按键、电阻和ADC输入负载，不能仅凭源码一致就认定可直接接线。验证器只接受这一明确例外，仍禁止其他设备占用保留引脚。

## RS-485与网关

| 选定JSM485模块丝印 | 每块STM32 |
| --- | --- |
| 3V3 / GND | 本板3.3V / 本板地 |
| TXD | PA2 / USART2_TX |
| RXD | PA3 / USART2_RX |
| NC | 悬空 |

同名TXD/RXD接法仅适用于用户选择、商品图已核对的JSM485版本，收到实物仍需核对；不能套用到其他TTL模块。旧ESP8266对PA2/PA3的连接不得同时占用该串口。

**GW-01 → CTRL-04 → CTRL-03 → CTRL-02 → CTRL-01。** A接A、B接B，用同一对双绞线；非隔离低压台架共参考地，负载回流不经细通信地。仅实际两端GW-01/CTRL-01接入120Ω，中间三个模块关闭。缩小台架时按当时物理端点调整。

四从站地址与板号一致，19200、8E1；S3网关GPIO17 TX→模块TXD，GPIO18 RX←模块RXD，需核对开发板引出与占用。另一个小智S3不接总线。共需5个485模块。业务协议是0x0200版，详见[四节点固件说明](../../../firmware/four-controller/README.md)；03读取保持寄存器，04读取96个输入寄存器，0x10原子写命令，不能把03/04当成相同输入表。

## 双屏与摇杆

| 屏幕丝印 | 1号/2号板引脚 | 用途 |
| --- | --- | --- |
| VCC / GND | 3.3V / 本板地 | 沿模块额定条件 |
| SCL | PB3 | SPI3时钟 |
| SDA | PB5 | SPI3 MOSI |
| RES | PB6 | 复位 |
| DC | PB7 | 命令/数据 |
| CS | PB8 | 片选 |
| BLK | PB9 | 背光控制接口 |

PB3/PB5使用SPI3，关闭JTAG并保留SWD；MISO/PB4与硬件NSS/PA15不接。BLK只接适配的控制输入/驱动，GPIO不承担未知背光电流。两块屏幕各接本区板，不互接屏幕线。

| 摇杆丝印 | CTRL-02引脚 |
| --- | --- |
| VCC / GND | 3.3V / 本板地 |
| VRx / VRy | PC0 / ADC1_IN10；PC1 / ADC1_IN11 |
| SW | PC4，上拉输入，按下接地 |

菜单读取本区摇杆；查看远端数据、确认远端命令由S3网关传递。断网/断总线时显示过期或未知，不能用远端旧值宣称实时；确认前、取消后均不产生动作。

## 31路传感器逐项对照

MQ-2接DO，MQ-4/CO接AO，火焰/液位接DO；SHT列SCL/SDA顺序。以下是源码对照表，实物仍需逐线核对。

### CTRL-01 / 左下

| 标签 | 站点 | 模块信号 → 本板引脚 | 采集方式 |
| --- | --- | --- | --- |
| MQ2-03 | P3 | DO→PC4 | GPIO输入 |
| MQ4-03 | P3 | AO→PA4 | ADC1_IN4 |
| CO-03 | P3 | AO→PA5 | ADC1_IN5 |
| FLAME-03 | P3 | DO→PB14 | GPIO输入 |
| MQ2-05 | P5 | DO→PC5 | GPIO输入 |
| MQ4-05 | P5 | AO→PA6 | ADC1_IN6 |
| CO-05 | P5 | AO→PA7 | ADC1_IN7 |
| FLAME-05 | P5 | DO→PC7 | GPIO输入 |
| SHT-03 | 本区附加 | SCL→PB10；SDA→PB11 | 软件I²C，0x44 |
| LEVEL-03 | 本区附加 | DO→PB1 | GPIO输入 |
| O2-02 | 本区附加 | 正极（不加电）→PA0 | ADC1_IN0 |

### CTRL-02 / 右下

| 标签 | 站点 | 模块信号 → 本板引脚 | 采集方式 |
| --- | --- | --- | --- |
| MQ2-04 | P4 | DO→PB12 | GPIO输入 |
| MQ4-04 | P4 | AO→PA4 | ADC1_IN4 |
| CO-04 | P4 | AO→PB0 | ADC1_IN8 |
| FLAME-04 | P4 | DO→PC6 | GPIO输入 |
| SHT-04 | 本区附加 | SCL→PB10；SDA→PB11 | 软件I²C，0x45 |
| LEVEL-04 | 本区附加 | DO→PC10 | GPIO输入 |
| O2-03 | 本区附加 | 正极（不加电）→PA6 | ADC1_IN6 |

### CTRL-03 / 右上

| 标签 | 站点 | 模块信号 → 本板引脚 | 采集方式 |
| --- | --- | --- | --- |
| MQ2-02 | P2 | DO→PB12 | GPIO输入 |
| MQ4-02 | P2 | AO→PA4 | ADC1_IN4 |
| CO-02 | P2 | AO→PC3 | ADC1_IN13 |
| FLAME-02 | P2 | DO→PC6 | GPIO输入 |
| SHT-02 | 本区附加 | SCL→PB10；SDA→PB11 | 软件I²C，0x45 |
| LEVEL-02 | 本区附加 | DO→PC12 | GPIO输入 |

### CTRL-04 / 左上

| 标签 | 站点 | 模块信号 → 本板引脚 | 采集方式 |
| --- | --- | --- | --- |
| MQ2-01 | P1 | DO→PB12 | GPIO输入 |
| MQ4-01 | P1 | AO→PC2 | ADC1_IN12 |
| CO-01 | P1 | AO→PC1 | ADC1_IN11 |
| FLAME-01 | P1 | DO→PB14 | GPIO输入 |
| SHT-01 | 本区附加 | SCL→PB6；SDA→PB7 | 软件I²C，0x44 |
| LEVEL-01 | 本区附加 | DO→PC0 | GPIO输入 |
| O2-01 | 本区附加 | 正极（不加电）→PC3 | ADC1_IN13 |

### 电源与测量边界

- MQ/液位按用户确认的5V模块供电、3.3V输出方案；5V供电不代表ADC可承受5V，实物不同批次仍须测量。火焰和SHT沿既有3.3V方案。原始ADC不是已标定ppm。
- AO-02裸探头不加电，正极接ADC、负极接本区模拟参考地。保留用户选择的直连，不新增调理器；低输出、ADC量化、输入负载与失调限制未消除，只上报raw/mV，不能当作标定氧浓度。
- 四区I²C各自独立，仅3.3V上拉；SHT-01/03为0x44、SHT-02/04为0x45，INA226为0x40，实物地址及总线波形待测。
- 不并联多板3.3V输出。MQ加热、灯带、风机用已核算的独立负载支路；当前表不等于电源容量已验收。

## 风机与其他执行器

| 设备 | 主控 | 引脚/接口 |
| --- | --- | --- |
| FAN-01 | CTRL-04 | PB8 / TIM4_CH3→PWM驱动；PA7←3.3V适配TACH |
| RELAY-01 | CTRL-04 | PA1→兼容驱动/IN1 |
| INA226-FAN1 | CTRL-04 | PB6/PB7；0x40 |
| FAN-02 | CTRL-02 | PB1 / TIM3_CH4→PWM驱动；PA7←3.3V适配TACH |
| RELAY-02 | CTRL-02 | PA1→兼容驱动/IN2 |
| INA226-FAN2 | CTRL-02 | PB10/PB11；0x40 |
| 蜂鸣器 | CTRL-03 | PB0→原驱动输入 |
| WS2812 18颗 | CTRL-03 | PB15 / SPI2_MOSI→原兼容电平转换→DIN |

候选功率回路为受保护12V支路→继电器COM/NO→INA高侧采样通路→风机正极；负极回本区负载回路。PWM/TACH的上拉、外部NPN反相、继电器有效电平、INA模块分流电阻和灯带电压都需实物核对。默认每转2脉冲与0.1Ω分流只是可配置候选，不是已测参数。

两路继电器若共用一块PCB，必须保留必要的跨区控制/功率线或调整板位，不能为声称零跨区而暗增硬件。左上4号PC10继续保留空闲。中央P5到1号为独立线束，具体长度未测。

## 资源、时序与断线行为

| 主控 | 实际源码资源 |
| --- | --- |
| CTRL-01 | SPI3屏幕轮询、ADC1轮询、软件I²C、USART2中断接收 |
| CTRL-02 | SPI3屏幕轮询、ADC1含摇杆、TIM3_CH4、EXTI7、软件I²C、USART2 |
| CTRL-03 | SPI2灯带/DMA1_CH5、ADC1轮询、软件I²C、USART2 |
| CTRL-04 | ADC1轮询、TIM4_CH3、EXTI7、软件I²C、USART2 |

ADC和屏幕DMA仍只是预留候选；当前实际使用的DMA是3号SPI2_TX/DMA1_CH5。USART1日志不使用同一DMA。数字输入由1 ms SysTick观察并消抖，对已观察事件锁存10秒；短于可观察窗口的脉冲不能保证捕获，IRQ抖动与时序须台架测量。

SWD PA13/PA14、USART1 PA9/PA10、USB PA11/PA12、BOOT、晶振保留；PA8/PC8/PC9等板载资源避免占用。PA0只有上述O2-02未验证例外，不等于释放所有板的WKUP引脚。

网关失效后，各STM32仍执行自身采集和已定义的本区保护；1号无直接风机/集中蜂鸣器，不能完成跨区联动。手动输出有有限租期，本地保护优先；软件PWM/继电器状态或命令回执不能证明实物转动，应结合新鲜TACH、电流和供电反馈。

## 重建与验收顺序

```powershell
python docs/hardware/four-controller-wiring-20261026/generate_plan.py
python docs/hardware/four-controller-wiring-20261026/validate_wiring.py
```

生成器校验历史基础JSON哈希后产生本表、机器接线表和逐线CSV；校验器独立检查31路、归属、GPIO/ADC/AF/I²C/DMA、保留脚例外及当前传感器源码。CSV每行是一根信号线，不是一个物理模块。

静态通过和编译通过均不能代替实物验收。按断电逐线核对→一主一从485→四节点身份和断线→本地采集→屏幕/摇杆→分别测风机/INA→灯带负载的顺序验证；每次记录实际板号、固件哈希、波形和现象。原诊断固件签名0x4853与业务固件0x5554不同，不混用验收结论。

参考：[STM32F103RC DS5792](https://www.st.com/resource/en/datasheet/stm32f103rc.pdf)、[RM0008](https://www.st.com/resource/en/reference_manual/rm0008-stm32f101xx-stm32f102xx-stm32f103xx-stm32f105xx-and-stm32f107xx-advanced-armbased-32bit-mcus-stmicroelectronics.pdf)、[历史接线依据](../four-controller-wiring-20261024/README.md)。
