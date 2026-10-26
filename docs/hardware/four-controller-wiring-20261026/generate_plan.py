"""Generate the new local-wiring proposal, not firmware or live asset identities."""
from copy import deepcopy
from pathlib import Path
import csv
import hashlib
import json

ROOT = Path(__file__).resolve().parent
BASE = ROOT.parent / 'four-controller-wiring-20261024' / 'wiring-plan.json'
BASE_SHA = 'b6cbe34589d85cf287b4eaf09e12766ed06e669a8902d2bd31b01a5408a2a018'
RENUMBER = {'CTRL-01': 'CTRL-04', 'CTRL-02': 'CTRL-03',
            'CTRL-03': 'CTRL-01', 'CTRL-04': 'CTRL-02'}
SCREEN_PINS = [('SCL', 'PB3', 'SPI3_SCK'), ('SDA', 'PB5', 'SPI3_MOSI'),
               ('RES', 'PB6', 'GPIO_OUT'), ('DC', 'PB7', 'GPIO_OUT'),
               ('CS', 'PB9', 'GPIO_OUT'), ('BLK', 'PC12', 'GPIO_OUT')]
POSITIONS_ZH = {'LOWER_LEFT': '左下', 'LOWER_RIGHT': '右下',
                'UPPER_RIGHT': '右上', 'UPPER_LEFT': '左上'}


def main():
    raw = BASE.read_bytes()
    if hashlib.sha256(raw.replace(b'\r\n', b'\n')).hexdigest() != BASE_SHA:
        raise RuntimeError('Historical source changed; review before regenerating this proposal.')
    p = deepcopy(json.loads(raw))
    p.update(schemaVersion=2, date='2026-10-26', revision='0.3',
             status='STATIC_PIN_PROPOSAL_NOT_FIRMWARE_OR_HARDWARE_ACCEPTANCE')
    p['source'] = {'path': str(BASE.relative_to(ROOT.parent.parent.parent)).replace('\\', '/'),
                   'sha256': BASE_SHA, 'hashPolicy': 'UTF8_BYTES_WITH_CRLF_NORMALIZED_TO_LF', 'generator': 'generate_plan.py',
                   'userDecision': '../2026-10-26-四主控编号与双屏布局确认.md'}
    p['identityMigration'] = {'previousPlannedNodeToNewPhysicalNode': RENUMBER,
        'liveDatabaseChanged': False, 'mqttChanged': False, 'modelChanged': False,
        'note': 'New CTRL codes identify the proposed physical numbering only; retain legacy asset tags and migrate explicitly.'}
    p['layout']['controllerPositions'] = {RENUMBER[n]: v for n, v in p['layout']['controllerPositions'].items()}
    for station in p['layout']['stations'].values():
        station['node'] = RENUMBER[station['node']]
    p['allocation'] = {RENUMBER[n]: v for n, v in p['allocation'].items()}
    p['nodeSpecificReserved'] = {RENUMBER[n]: v for n, v in p['nodeSpecificReserved'].items()}
    for sensor in p['sensors']:
        sensor['previousPlan'] = {'node': sensor['node'], 'pins': list(sensor['pins'])}
        sensor['node'] = RENUMBER[sensor['node']]
        sensor['localZone'] = p['layout']['controllerPositions'][sensor['node']]
        # The nested `old` field remains the actual historical wiring evidence.
    for bus in p['buses']:
        bus['node'] = RENUMBER[bus['node']]
    for device in p['devices']:
        device['previousPlan'] = {'node': device['node'], 'signals': deepcopy(device['signals'])}
        device['node'] = RENUMBER[device['node']]
        if device['id'] in ('SCREEN-STATUS', 'SCREEN-MAIN'):
            device['node'] = 'CTRL-01' if device['id'] == 'SCREEN-STATUS' else 'CTRL-02'
            device['signals'] = [dict(name=n, pin=pin, mode=mode) for n, pin, mode in SCREEN_PINS]
            device['power'] = '3V3_MODULE_RATING_AND_BACKLIGHT_INTERFACE_TO_VERIFY'
            device['spiSetup'] = 'SPI3_MASTER_TX_ONLY_SOFTWARE_NSS_NO_REMAP; DISABLE_JTAG_RETAIN_SWD'
        if device['id'] == 'JOYSTICK':
            device['node'] = 'CTRL-02'
        device['localZone'] = p['layout']['controllerPositions'][device['node']]
    p['rs485']['route'] = ['GW-01', 'CTRL-04', 'CTRL-03', 'CTRL-02', 'CTRL-01']
    p['rs485']['terminations'] = ['GW-01', 'CTRL-01']
    p['rs485']['slaveAddressProposal'] = {f'CTRL-0{i}': i for i in range(1, 5)}
    p['powerBudget']['mqModuleCounts'] = {RENUMBER[n]: v for n, v in p['powerBudget']['mqModuleCounts'].items()}
    p['userConfirmations']['layoutDate'] = '2026-10-26'
    p['userConfirmations']['layout'] = 'LOWER_LEFT_1_LOWER_RIGHT_2_UPPER_RIGHT_3_UPPER_LEFT_4; SCREENS_ON_1_AND_2'
    p['userConfirmations']['locality'] = 'MINIMIZE_CROSS_ZONE_WIRING_USE_NEAREST_CONTROLLER'
    p['userConfirmations']['fanReplan'] = 'RETAIN_PHYSICAL_FANS_AND_PB8_PWM_PA7_TACH_PA1_RELAY; NEW_NODES_CTRL04_AND_CTRL02'
    p['implementationDefaults'] = {'joystickNode': 'CTRL-02', 'mainScreenNode': 'CTRL-02',
        'statusScreenNode': 'CTRL-01', 'sensorPinsUnchangedWithinPhysicalZones': True,
        'buzzerAndLedNode': 'CTRL-03', 'mainScreenDoesNotOwnRemoteOutputs': True}
    p['fanPlan']['document'] = 'README.md#风机与其他执行器'
    p['fanPlan']['placement'] = 'FAN01_UPPER_LEFT_CTRL04; FAN02_LOWER_RIGHT_CTRL02; PHYSICAL_LOCATIONS_UNCHANGED'
    p['dmaProposal'] = [
        {'node': 'CTRL-01', 'channel': 'DMA2_CH2', 'request': 'SPI3_TX'},
        {'node': 'CTRL-02', 'channel': 'DMA2_CH2', 'request': 'SPI3_TX'},
        {'node': 'CTRL-03', 'channel': 'DMA1_CH5', 'request': 'SPI2_TX'},
        *[{'node': f'CTRL-0{i}', 'channel': 'DMA1_CH1', 'request': 'ADC1'} for i in range(1, 5)],
    ]
    p['extiPolicy'] = 'FAN_TACH_PA7_EXTI7_ON_CTRL02_AND_CTRL04_ONLY; SENSOR_DO_AND_JOYSTICK_SW_POLLED'
    p['locality'] = {'rule': 'KEEP_PHYSICAL_SENSOR_ZONES; NO_REMOTE_GPIO_ADC_I2C_SCREEN_WIRES',
        'centerStation': 'P5_TO_LOWER_LEFT_CTRL01_SINGLE_LOCAL_HARNESS',
        'remoteActions': 'LOCAL_OUTPUT_OWNER_EXECUTES_ADDRESSED_REQUESTS_VIA_GATEWAY_NOT_IMPLEMENTED',
        'relayPcb': 'REUSE_EXISTING; IF_SHARED_DUAL_CHANNEL_BOARD_ONE_LONGER_CONTROL_OR_LOAD_HARNESS_MAY_BE_UNAVOIDABLE',
        'lengthsMeasured': False}
    p['evidence']['datasheetPinTable'] = 'DS5792 Rev13 Table8: PB3 SPI3_SCK; PB5 SPI3_MOSI; PA7 TIM3_CH2/ADC1_IN7 or EXTI7 GPIO'
    p['evidence']['halJtagMacro'] = 'firmware/stm32f103rct6/Drivers/STM32F1xx_HAL_Driver/Inc/stm32f1xx_hal_gpio_ex.h: __HAL_AFIO_REMAP_SWJ_NOJTAG'
    p['firmwareChanged'] = False
    p['hardwareTested'] = False
    (ROOT / 'wiring-plan.json').write_text(json.dumps(p, ensure_ascii=False, indent=2) + '\n', encoding='utf-8', newline='\n')
    write_csv(p)
    write_readme(p)
    print('Generated wiring-plan.json, wiring-connections.csv and README.md')


def connections(p):
    for s in p['sensors']:
        if s['interface'] == 'I2C_SOFTWARE':
            for name, pin in zip(('SCL', 'SDA'), s['pins']):
                yield s['node'], s['physicalTag'], s['station'] or '本区附加', name, pin, 'I2C_SOFTWARE', '3.3V上拉', s['previousPlan']['node']
        else:
            sig = '正极/毫伏输出' if s['category'] == 'O2' else ('AO' if s['interface'] == 'ADC' else 'DO')
            mode = f"ADC1_IN{s['adcChannel']}" if s['interface'] == 'ADC' else 'GPIO_INPUT_POLL'
            yield s['node'], s['physicalTag'], s['station'] or '本区附加', sig, s['pins'][0], mode, s['powerDomain'], s['previousPlan']['node']
    for b in p['buses']:
        for d in b['devices']:
            if d['id'].startswith('INA'):
                for name, pin in [('SCL', b['scl']), ('SDA', b['sda'])]:
                    yield b['node'], d['id'], '本区风机', name, pin, 'I2C_SOFTWARE', '逻辑3.3V；测量侧独立', ''
    for d in p['devices']:
        for s in d['signals']:
            yield d['node'], d['id'], POSITIONS_ZH[d['localZone']], s['name'], s['pin'], s['mode'], '见README接口条件', d['previousPlan']['node']


def write_csv(p):
    with (ROOT / 'wiring-connections.csv').open('w', encoding='utf-8-sig', newline='') as out:
        writer = csv.writer(out, lineterminator='\n')
        writer.writerow(['新主控', '设备实物标签', '分组', '模块信号', '主控引脚', '外设模式', '电源或接口说明', '10月24日规划主控'])
        writer.writerows(sorted(connections(p)))


def write_readme(p):
    lines = ['# 四主控就近接线与引脚表 V0.3', '',
        '2026-10-26。适用目标：STM32F103RCT6、原有ST7735S双屏和五针模拟摇杆。四块到货板的实际版本及排针引出仍需逐板核对。', '',
        '**本表取代10月24日的位置编号、设备归属和受影响的引脚表。按用户图：左下1、右下2、右上3、左上4；屏幕在1/2号，摇杆默认接2号。各设备就近接所属板。**', '',
        '这是完整的接线设计，静态检查结果见[validation-report.json](validation-report.json)。尚未修改/编译四节点固件、烧录或实物验收；不能将旧两节点镜像接到新线后直接运行。', '',
        '## 布局与就近原则', '', '```text',
        '        网关GW-01（左上干区）',
        '        │',
        '   4号/P1 ─────────── 3号/P2',
        '   风机1              蜂鸣器、灯带',
        '                           │',
        '            P5             │',
        '             ╲             │',
        '   1号/P3 ─────────── 2号/P4',
        '   状态屏、P5线束      主屏、摇杆、风机2',
        '```', '',
        '图中的横竖主干只表示485路径；P5斜线是单独传感器线束，不接入A/B。局部传感器不跨区拉ADC/DO/I²C；风机、继电器驱动与INA测量回路尽量放在对应风机附近。两屏均放在所属底部区域。', '',
        '| 新主控 | 位置 | 检测站 | 外部模块数 | 其他本地设备 |',
        '| --- | --- | --- | ---: | --- |',
        '| 1号/CTRL-01 | 左下 | P3＋中央P5 | 11 | 状态屏 |',
        '| 2号/CTRL-02 | 右下 | P4 | 7 | 主屏、摇杆、风机2、继电器2、INA226-FAN2 |',
        '| 3号/CTRL-03 | 右上 | P2 | 6 | 蜂鸣器、18颗灯带 |',
        '| 4号/CTRL-04 | 左上 | P1 | 7 | 风机1、继电器1、INA226-FAN1 |', '',
        'P1～P5和传感器尾号保持原空间含义，不跟着新主控编号重排。31路按物理模块计，温湿度两个指标只计一个模块；INA226另列。新CTRL编码只作为新接线/固件目标；旧数据库、MQTT身份、模型绑定和历史数据没有重命名，接入前须显式迁移。', '',
        '旧规划左下CTRL-03→新1号、右下CTRL-04→新2号、右上CTRL-02→新3号、左上CTRL-01→新4号。**按板上实际新标签施工，不能按旧NodeA/NodeB或COM口猜身份。**', '',
        '## 四板通用RS-485', '',
        '| 所选JSM485模块丝印 | 每块STM32 |', '| --- | --- |',
        '| 3V3 | 本板3.3V |', '| GND | 本板GND |',
        '| TXD | PA2 / USART2_TX |', '| RXD | PA3 / USART2_RX |', '| NC | 悬空 |', '',
        'TXD/RXD同名接法仅针对已选、商品图已核对的JSM485，不能套用未知模块；收到的实物丝印仍需核对。旧ESP8266占用PA2/PA3的线先断开。', '',
        '**主干：GW-01 → 4号 → 3号 → 2号 → 1号，末端不闭合。** A接A、B接B，A/B用同一对双绞线。非隔离低压台架共参考地，负载回流不走细通信地。只有GW-01和1号的120Ω/SW1开，中间4/3/2号关闭。起步仅接网关＋一块板时，终端随当时的两个物理端点调整。', '',
        '网关候选GPIO17 TX→模块TXD，GPIO18 RX←模块RXD，需核对S3具体板型、引出和其他占用；另一个语音S3不接本总线。四板＋网关共需5个模块。候选从站地址与板号同为1～4；19200、8E1是协议待实现参数，不是现有固件已支持的配置。', '',
        '## 1号和2号屏幕：统一接法', '',
        '| ST7735S屏幕丝印 | 所属板引脚 | 用途 |', '| --- | --- | --- |',
        '| VCC | 3.3V | 沿原模块电源条件 |', '| GND | GND | 本板地 |']
    desc = {'SCL': 'SPI3时钟，不是I²C', 'SDA': 'SPI3发送/MOSI，不是I²C',
            'RES': '复位输出', 'DC': '命令/数据选择', 'CS': 'GPIO片选', 'BLK': '背光控制接口'}
    lines += [f'| {n} | {pin} | {desc[n]} |' for n, pin, _ in SCREEN_PINS]
    lines += ['',
        '两块屏幕分别接自己所在的1号/2号板，不互接屏幕线。PB3/PB5使用硬件SPI3、单线发送、软件NSS；MISO/PB4和硬件NSS/PA15不接。初始化须启用AFIO、关闭JTAG但保留SWD，例如`__HAL_AFIO_REMAP_SWJ_NOJTAG()`；这不是关闭调试接口。BLK仅接已确认的背光控制输入/驱动，不从GPIO直接提供未知背光电流。', '',
        '统一SPI3避开右下2号风机TACH的PA7及PWM的PB8，也避开左下1号氧气的PA5和中央火焰的PC7。新方案没有用SPI1屏幕线去占这些信号。', '',
        '## 2号摇杆', '', '| 摇杆丝印 | 2号板引脚 | 说明 |', '| --- | --- | --- |',
        '| +5V/VCC | 3.3V | 沿原模块在3.3V使用，避免轴输出5V |', '| GND | GND | 本区参考地 |',
        '| VRx | PC0 / ADC1_IN10 | 方向随安装在软件中校正 |',
        '| VRy | PC1 / ADC1_IN11 | 同上 |',
        '| SW | PC4 / GPIO输入上拉 | 按下接地，软件扫描消抖 |', '',
        '菜单只在2号板读取摇杆；查看其他板的值、请求远端执行器动作通过485网关的寻址协议实现，不跨区拉摇杆/控制GPIO。该协议和菜单固件尚未实现。', '',
        '## 各区31路传感器', '',
        '以下引脚沿用原物理区域的传感器接入点，只更新主控位置编号。SHT为SCL/SDA顺序；MQ2只接DO，MQ4/CO接AO，火焰/液位接DO。CO实物沿原MQ-7类模块。', '']
    for node in sorted(p['allocation']):
        lines += [f"### {node} / {POSITIONS_ZH[p['layout']['controllerPositions'][node]]}", '',
                  '| 实物标签 | 站点 | 模块信号 → 本板引脚 | 采集方式 |', '| --- | --- | --- | --- |']
        for s in [s for s in p['sensors'] if s['node'] == node]:
            if s['interface'] == 'I2C_SOFTWARE':
                conn = f"SCL→{s['pins'][0]}；SDA→{s['pins'][1]}"
                mode = f"软件I²C，0x{s['i2cAddress']:02X}"
            else:
                sig = '正极（不加电）' if s['category'] == 'O2' else ('AO' if s['interface'] == 'ADC' else 'DO')
                conn = f"{sig}→{s['pins'][0]}"
                mode = f"ADC1_IN{s['adcChannel']}" if s['interface'] == 'ADC' else 'GPIO扫描输入'
            lines.append(f"| {s['physicalTag']} | {s['station'] or '本区附加'} | {conn} | {mode} |")
        lines.append('')
    lines += ['### 电源和信号条件', '',
        '- MQ/液位沿已确认的模块5V供电方案，用户此前确认其信号为3.3V；供电5V不等于ADC可接5V。火焰、SHT按既有3.3V模块方案。不同实物版本需先核对；原始ADC不当作标定ppm。',
        '- AO-02裸氧气电极不加电：正极接表中ADC，负极接本区模拟参考地；保留用户选择的毫伏直连方式，不新增调理板。低输出、ADC量化和失调限制未消除，只能作为原始值试验，不能声称精确氧浓度。',
        '- 四区各自的I²C总线不互连，初期软件I²C目标100kHz、仅3.3V上拉。SHT-01/03沿用0x44、SHT-02/04沿用0x45；同区INA为0x40，实际扫描确认。',
        '- 每块板3.3V只供本区已核算的逻辑负载，不能并联多板3.3V输出；MQ加热、灯带、风机负载用对应独立电源支路。', '',
        '## 风机与其他执行器', '', '| 设备 | 所属新主控 | 引脚/接口 |', '| --- | --- | --- |',
        '| FAN-01 / 左上风机 | 4号 | PB8→PWM驱动；PA7←适配到3.3V的TACH |',
        '| RELAY-01 | 4号 | PA1→原兼容驱动/IN1 |',
        '| INA226-FAN1 | 4号 | SCL=PB6，SDA=PB7，地址0x40 |',
        '| FAN-02 / 右下风机 | 2号 | PB8→PWM驱动；PA7←适配到3.3V的TACH |',
        '| RELAY-02 | 2号 | PA1→原兼容驱动/IN2 |',
        '| INA226-FAN2 | 2号 | SCL=PB10，SDA=PB11，地址0x40 |',
        '| 蜂鸣器 / 右上 | 3号 | PB0→原蜂鸣器驱动输入 |',
        '| 18颗WS2812 / 右上馈入 | 3号 | PB15 / SPI2_MOSI→原74AHCT/HCT电平转换→DIN |', '',
        '风机供电/继电器/INA功率回路按原功能顺序：12V受保护支路→继电器COM/NO→INA高侧采样通路→风机正极；负极回本区负载回路。逻辑电源、测量端及触点分别按实际模块丝印核对。PWM经过兼容开集电极/开漏驱动，不能直连内部高电压上拉；TACH也须3.3V兼容。旧PC10/PA15/PB9等风机控制线先断开，不能与新输出并接；左上4号PC10保留空闲。', '',
        '沿用原风机PWM目标25kHz、每转2脉冲候选值，须用实际风机验证。默认继电器不吸合、蜂鸣器/灯带关闭的物理有效电平和外部偏置待上电核对；0%PWM或命令回执不能证明停转。', '',
        '**就近限制：** 若现有两路继电器共用一块PCB，它不能同时位于两个对角。优先复用现有板并让功率线靠负载敷设；保留一束必要的较长控制线或调整板位，不能为了声称零跨区而把PCB拆开或暗加新模块。蜂鸣器/灯带按原布局保留右上3号；实际安装若移动，再按最近板调整。中央P5到1号是独立的短线束规划，尚未测量具体线长。', '',
        '## 固件资源核对', '', '| 板 | 资源 | DMA候选（尚未实现） |', '| --- | --- | --- |',
        '| 1号 | SPI3屏幕、ADC1、软件I²C、USART2 | 屏DMA2_CH2；ADC DMA1_CH1 |',
        '| 2号 | SPI3屏幕、ADC1含摇杆、TIM4_CH3风机、EXTI7测速、软件I²C、USART2 | 屏DMA2_CH2；ADC DMA1_CH1 |',
        '| 3号 | SPI2灯带、ADC1、软件I²C、USART2 | 灯带DMA1_CH5；ADC DMA1_CH1 |',
        '| 4号 | ADC1、TIM4_CH3风机、EXTI7测速、软件I²C、USART2 | ADC DMA1_CH1 |', '',
        'USART1的PA9/PA10保留下载/日志，采用中断/轮询，特别是不与3号灯带共占DMA1_CH5；USART2先采用中断收发，不占用额外DMA候选。两块不同MCU上的同号DMA独立，不构成冲突。TIM4只分配风机CH3，不同时将屏幕控制脚当定时器通道使用。数字传感器和摇杆按键扫描/锁存，不同时给PB13和PC13配置同一个EXTI13；风机EXTI7只在2/4号各自使用PA7。', '',
        '保留SWD PA13/PA14、USART1 PA9/PA10、USB PA11/PA12、BOOT、晶振；按库存板避开PA0/PC8/PC9板载按键和PA8板载LED。1/2号使用PB3时关闭JTAG且保持SWD，PB4/PA15继续不接新增设备。PC13只作液位输入，不驱动背光等负载。', '',
        '1号没有直接连接风机或集中蜂鸣器，P3/P5到其他板的联动仍依赖网关；菜单板也不接远端执行器的GPIO。离线后各区能力按真实连接降级，不宣称四区独立完成所有联动。', '',
        '## 生成、检查和接线顺序', '', '```powershell',
        'python docs/hardware/four-controller-wiring-20261026/generate_plan.py',
        'python docs/hardware/four-controller-wiring-20261026/validate_wiring.py', '```', '',
        '`generate_plan.py`是此版本生成源，校验10月24日基础JSON哈希后产生本表、[机器接线表](wiring-plan.json)与[逐线CSV](wiring-connections.csv)。原基础JSON、历史接线和固件没有被覆盖；CSV一行是信号线，不是一个物理传感器。', '',
        '先贴四板新编号、标记旧线并断电核对→每区先连接485→一主一从新固件通信→各区SHT/数字输入→模拟输入→1/2号屏幕及摇杆→分别接风机→灯带和语音并行负载。新四节点固件和网关轮询协议尚需开发；不要把旧主动串口JSON镜像并到共享485。', '',
        '静态验证核对31路唯一身份、就近归属、GPIO重用、实际外设引脚、ADC通道、屏幕/摇杆位置、I²C地址、DMA候选及主干终端。通过只证明规划资源一致，不代表到货板卡、电平、供电、驱动或整机已实测。', '',
        '依据：[STM32F103RC DS5792引脚表](https://www.st.com/resource/en/datasheet/stm32f103rc.pdf)、[RM0008](https://www.st.com/resource/en/reference_manual/rm0008-stm32f101xx-stm32f102xx-stm32f103xx-stm32f105xx-and-stm32f107xx-advanced-armbased-32bit-mcus-stmicroelectronics.pdf)、项目既有HAL宏及[历史接线依据](../four-controller-wiring-20261024/README.md)。', '']
    (ROOT / 'README.md').write_text('\n'.join(lines), encoding='utf-8', newline='\n')


if __name__ == '__main__':
    main()
