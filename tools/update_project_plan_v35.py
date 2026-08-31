from copy import deepcopy
from pathlib import Path

from docx import Document
from docx.enum.text import WD_BREAK


SOURCE = Path(r"D:\shixi\docs\综合管廊数字孪生运维实体样品项目计划书_V3.4_当前进度与执行计划版.docx")
OUTPUT = Path(r"D:\shixi\docs\综合管廊数字孪生运维实体样品项目计划书_V3.5_硬件数量与型号冻结版.docx")


def set_cell(cell, text):
    cell.text = text


def row_by_code(table, code):
    for row in table.rows[1:]:
        if row.cells[0].text.strip() == code:
            return row
    raise KeyError(code)


def set_bom(table, code, name, qty, purpose, estimate):
    row = row_by_code(table, code)
    values = (code, name, qty, purpose, estimate)
    for cell, value in zip(row.cells, values):
        set_cell(cell, value)


def add_bom(table, code, name, qty, purpose, estimate):
    row = table.add_row()
    for cell, value in zip(row.cells, (code, name, qty, purpose, estimate)):
        set_cell(cell, value)


def add_interface(table, module, pin, electrical, constraint):
    row = table.add_row()
    for cell, value in zip(row.cells, (module, pin, electrical, constraint)):
        set_cell(cell, value)


def add_ledger(table, asset, hardware, purpose, limits):
    row = table.add_row()
    for cell, value in zip(row.cells, (asset, hardware, purpose, limits)):
        set_cell(cell, value)


def add_status(table, domain, status, fact, gap):
    row = table.add_row()
    for cell, value in zip(row.cells, (domain, status, fact, gap)):
        set_cell(cell, value)


doc = Document(SOURCE)

# 封面与页眉的版本信息属于文档元数据，需与V3.5正文一致。
for section in doc.sections:
    for paragraph in section.header.paragraphs:
        if "项目计划书 V3.4" in paragraph.text:
            paragraph.text = paragraph.text.replace("项目计划书 V3.4", "项目计划书 V3.5")
if "最近更新：2026年8月29日" in doc.paragraphs[4].text:
    doc.paragraphs[4].text = doc.paragraphs[4].text.replace("最近更新：2026年8月29日", "最近更新：2026年8月31日")

# 文档版本与采购说明
table0 = doc.tables[0]
set_cell(table0.rows[1].cells[1], "V3.5（硬件数量与型号冻结版）")
set_cell(
    table0.rows[6].cells[1],
    "V3.5按实物清单补充传感器数量、通信/控制模块与执行器型号；未给出规格的器件保留待核验项。",
)

procurement_note = doc.paragraphs[107]
procurement_note.add_run(
    "\nV3.5硬件数量冻结：氧气、CO、甲烷、烟雾、火焰、温湿度六类传感器均按每类5个记录；"
    "新增模块与执行器均按实物型号登记。DCP-3620的功能、电压、接口与数据手册尚未提供，"
    "仅作为待核验物料，禁止据此假定引脚、电源或控制用途。"
)

# 7.1 BOM
bom = doc.tables[21]
set_bom(
    bom, "H-02", "ESP8266-01S Wi-Fi模块及转接板", "2",
    "1个作为STM32串口-MQTT主链路，1个备用；均需独立3.3V稳压、EN/RST与掉电重连验证。", "30-60",
)
set_bom(
    bom, "H-03", "SHT30 / DHT22 温湿度模块", "5",
    "温湿度传感器数量基线；每个实物接入前确认I²C/单总线、供电电压和校验方式。", "待报价",
)
set_bom(
    bom, "H-04", "DS18B20防水温度探头（备选）", "0（不计入本轮数量基线）",
    "如后续保留分区温度探头，须另行冻结数量与接口；不能与V3.5温湿度模块数量基线混淆。", "待定",
)
set_bom(
    bom, "H-05", "MQ-4 甲烷传感器模块", "5",
    "真实在线采集环境基线；越限演示仅由隔离信号模拟盒生成，禁止释放可燃气体。", "待报价",
)
set_bom(
    bom, "H-06", "MQ-7 一氧化碳传感器模块", "5",
    "真实在线采集环境基线；禁止使用CO气体测试，须记录预热与交叉敏感边界。", "待报价",
)
set_bom(
    bom, "H-07", "ME2-O2 电化学氧气传感器及调理电路", "5",
    "真实在线采集环境基线；不得置换教室空气，量程与接口以实物数据手册为准。", "待报价",
)
set_bom(
    bom, "H-08", "MQ-2 烟雾气敏模块", "5",
    "烟雾/气敏演示模块；仅使用合规测试气雾或隔离信号模拟，不使用燃烧或可燃气体。", "待报价",
)
add_bom(
    bom, "H-08A", "火焰传感器（四线）", "5",
    "火焰感知扩展；接入前核验供电、DO/AO输出电平与抗环境光误报能力；不使用明火作为演示手段。", "待报价",
)
set_bom(
    bom, "H-12", "12V四线风机", "2",
    "两台低压风机；分别核验PWM、转速反馈、额定电流和转向，MCU不得直接驱动。", "待报价",
)
set_bom(
    bom, "H-18", "JQC-3FF-S-Z 继电器模块（1路）", "1",
    "低压负载通断；先核验线圈电压、触发电平、触点额定值及感性负载的续流/吸收保护。", "待报价",
)
set_bom(
    bom, "H-19", "12V电源、5V/3.3V降压、保险、急停", "1套",
    "分域供电与保护；24V水泵如需台架核验，必须采用独立、受保险保护的24V支路。", "150-300",
)
add_bom(
    bom, "H-21A", "24V水泵", "1",
    "已登记库存硬件；当前干燥管廊水浸演示不启用该泵，不连接建筑给水，不构建循环水路。若后续使用须单独完成水电隔离、安全评审与变更批准。", "待报价",
)
add_bom(
    bom, "H-25", "K210可视化模块", "1",
    "后续视觉事件采集与识别扩展；不作为当前报警联动的唯一依据。", "待报价",
)
add_bom(
    bom, "H-26", "SU-03T1语音识别模块", "1",
    "本地语音交互扩展；接入前确认离线词表、UART协议、供电及误唤醒处理。", "待报价",
)
add_bom(
    bom, "H-27", "DCP-3620", "1",
    "用户提供型号；功能、电压、电流、接口和项目用途待以实物标签/数据手册核验后冻结。", "待报价",
)
add_bom(
    bom, "H-28", "多通道ADC与模拟调理板", "1套（通道数待设计冻结）",
    "为5个ME2-O2与15个MQ模块的模拟信号预留采集/调理；须按实际输出范围、精度、隔离与3.3V ADC边界确定通道数，不能直接把5V模拟量接入STM32。", "待选型",
)
add_bom(
    bom, "H-29", "I²C多路复用器（若选SHT30）", "1",
    "5个同地址SHT30需通过多路复用器或改用DHT22独立GPIO方案；二者择一后冻结。", "待选型",
)
add_bom(
    bom, "H-30", "MQ传感器加热与采样驱动", "15路",
    "MQ-4、MQ-7、MQ-2各5个；独立核算5V加热电流、保险与MOSFET控制。MQ-7的加热/采样时序必须按数据手册验证。", "待设计",
)
add_bom(
    bom, "H-31", "四线风机PWM/TACH接口与保护", "2路",
    "每台12V四线风机各需一路PWM开漏控制、一路TACH输入整形/上拉与独立保险；JQC继电器不替代此接口。", "待设计",
)
add_bom(
    bom, "H-32", "24V水泵驱动、保险与浪涌保护", "1套（后置）",
    "仅为库存水泵的后续合规台架核验预留；当前水浸演示禁用，不接建筑给水，不形成循环水路。", "待设计",
)
add_bom(
    bom, "H-33", "传感器端子、插座、线束与资产标签", "不少于30个传感器端口",
    "覆盖六类传感器各5个，并为水浸/水位、门磁、风机反馈和执行器保留独立端子、编号、应力释放与干湿隔离。", "待报价",
)
add_bom(
    bom, "H-34", "K210/SU-03T1配套件", "按实物核验",
    "确认K210是否含摄像头、连接线与存储卡；确认SU-03T1是否含麦克风/扬声器。缺失配件不得以软件假定替代。", "待核验",
)

# 传感器与水路安全口径
logic = doc.tables[22]
set_cell(logic.rows[1].cells[1], "甲烷采用MQ-4模块，CO采用MQ-7模块，氧气采用ME2-O2电化学传感器及调理电路；每类均为5个。它们的供电、预热、量程、标定与交叉敏感以实物数据手册为准。")
set_cell(logic.rows[2].cells[1], "MQ系列适合存在性/趋势演示，但需要长时间预热、受温湿度和交叉气体影响，不能承担准确浓度或安全联锁。V3.5将MQ-4、MQ-7、MQ-2各按5个登记，仍必须按模块数据手册验证与标定。")
set_cell(logic.rows[3].cells[1], "本样品是干燥管廊，不运行循环水工艺。24V水泵仅登记为库存硬件，当前水浸/水位演示仍只允许向独立接水盘加入不超过50mL清水；不接建筑给水、不形成循环水路，未经安全变更批准不得启用水泵。")

# 引脚表：新增模块明确为“待冻结”，避免假定接口
interface = doc.tables[23]
add_interface(interface, "ESP8266-01S（备用）", "未接入主控", "3.3V UART / 备用", "与主链路模块同型号；备用件不得并接到USART2，替换时需复测固件、供电和重连。")
add_interface(interface, "K210可视化模块", "待冻结", "待核验", "1个；接口、电源、摄像头与事件上报协议待确认，不占用当前MVP引脚。")
add_interface(interface, "SU-03T1语音识别模块", "待冻结", "待核验", "1个；需确认离线词表、UART/IO协议、供电与唤醒逻辑后再进入原理图。")
add_interface(interface, "JQC-3FF-S-Z继电器模块", "待冻结", "线圈/触点待核验", "1个；仅控制低压负载，驱动极性、续流/隔离和触点额定值未核验前不得接入。")
add_interface(interface, "12V四线风机 ×2 / 24V水泵 ×1", "待冻结", "分别独立供电", "风机核验PWM与TACH；水泵当前禁用于水浸演示，须单独安全变更后才可接线。")
add_interface(interface, "DCP-3620", "待冻结", "待核验", "1个；无数据手册不得分配供电或MCU引脚。")
add_interface(interface, "多传感器采集扩展", "待冻结", "ADC/模拟调理与I²C复用待设计", "5个ME2-O2、15个MQ和5个SHT30/DHT22不能以当前单通道样机表直接扩展；须先完成通道、电源与接口矩阵。")

# 状态表：固化实物数量与接入边界
status = doc.tables[46]
set_cell(status.rows[2].cells[2], "2个ESP8266-01S已登记；其中1个自定义Arduino串口-MQTT桥已烧录并与STM32实物连接，另1个为备用。")
set_cell(status.rows[2].cells[3], "补齐主模块接线照片、启动日志、#STATUS、#PUBLISHED、Broker日志和固件版本证据；备用模块仅在替换验证后投入主链路。")
set_cell(status.rows[10].cells[2], "K210可视化模块1个已纳入V3.5硬件清单；视觉仍是后续扩展。")
set_cell(status.rows[10].cells[3], "尚未实现；接口、电源和视觉事件协议待核验，不作为当前告警或联动依据。")
add_status(status, "语音/新增执行器与待核验模块", "待冻结", "SU-03T1×1、JQC-3FF-S-Z×1、12V四线风机×2、24V水泵×1、DCP-3620×1已纳入V3.5硬件台账。", "SU-03T1、DCP-3620及水泵的规格/接口未冻结；水泵当前不进入水浸演示；所有新增模块须完成数据手册、供电和台架测试。")
add_status(status, "V3.5多传感器接口与供电", "缺项待补", "六类传感器各5个已冻结，共30个传感器本体；其中MQ类15个、ME2-O2 5个、温湿度5个需纳入采集矩阵。", "需补多通道ADC/模拟调理、SHT30多路复用或DHT22 GPIO方案、MQ加热/采样电源、两路风机PWM/TACH接口、端子/标签和分域供电容量核算。")

# 采购优先级与预算口径
priority = doc.tables[53]
set_cell(priority.rows[1].cells[1], "甲烷MQ-4、CO MQ-7、ME2-O2、MQ-2烟雾、火焰、SHT30/DHT22传感器（每类5个）、多通道ADC/调理、MQ加热驱动、SHT30多路复用或DHT22 GPIO、STM32板、ESP8266-01S×2、烟感、水浸和高水位")
set_cell(priority.rows[1].cells[2], "决定核心场景且数量已按V3.5冻结；传感器本体与采集/供电接口必须成套到位后再做逐件通电、通信和合理性测试。")
set_cell(priority.rows[2].cells[1], "JQC-3FF-S-Z继电器、12V四线风机×2、低压电源/保护、端子、线材、高边接水盘、滴水器和吸水材料")
set_cell(priority.rows[3].cells[1], "K210、SU-03T1、DCP-3620与24V水泵（仅登记及规格核验，不得挤占MVP安全闭环）")
set_cell(priority.rows[3].cells[2], "接口/安全边界待确认；24V水泵不得用于当前水浸演示。")

budget = doc.tables[52]
set_cell(budget.rows[1].cells[2], "V3.5已增加六类传感器各5个、两块ESP8266、两台四线风机、K210、SU-03T1、DCP-3620、继电器与水泵；实际总额待型号和供应商报价复核。")
set_cell(budget.rows[2].cells[2], "气体/烟雾/火焰/温湿度传感器均按每类5个；水泵仅库存登记，不改变“无循环水路”边界。")
set_cell(budget.rows[5].cells[1], "待V3.5全部器件完成型号、电压与报价核验后更新")
set_cell(budget.rows[5].cells[2], "不把未核验的DCP-3620或水泵用途计入固定预算；以实际报价和安全评审为准。")
set_cell(budget.rows[6].cells[1], "待V3.5询价后更新")
set_cell(budget.rows[6].cells[2], "现有区间未包含全部新增数量与待核验模块；取得型号、数量、交期和报价后统一复核。")

# 附录E实物台账
ledger = doc.tables[62]
set_cell(ledger.rows[8].cells[1], "JQC-3FF-S-Z 1路继电器模块（1个）")
set_cell(ledger.rows[8].cells[2], "风机或照明等低压负载通断")
set_cell(ledger.rows[8].cells[3], "继电器触点与MCU低压侧隔离；仅控制样品低压负载。须核验线圈/触发电平、触点额定值及感性负载保护。")
set_cell(ledger.rows[9].cells[1], "12V四线风机（2个）")
set_cell(ledger.rows[9].cells[2], "通风联动与风机故障场景")
set_cell(ledger.rows[9].cells[3], "逐台确认额定电压、电流、PWM、TACH与转向；MCU不得直接带电机，须配置驱动与反馈。")
add_ledger(ledger, "H-26", "传感器数量基线：ME2-O2、MQ-7、MQ-4、MQ-2、火焰、SHT30/DHT22，各5个", "多点传感与冗余/对照台架", "所有模块上电前核验电压与输出逻辑；异常演示遵守隔离信号模拟、合规烟感测试与禁止危险气体/明火的安全边界。")
add_ledger(ledger, "H-27", "K210可视化模块（1个）", "后续视觉事件扩展", "不进入当前报警联动关键路径；先确认供电、摄像头、串口/网络协议与隐私边界。")
add_ledger(ledger, "H-28", "SU-03T1语音识别模块（1个）", "后续本地语音交互", "先确认供电、离线词表与UART/IO协议；语音命令不得绕过安全互锁或人工确认。")
add_ledger(ledger, "H-29", "DCP-3620（1个）", "用途待核验", "未提供数据手册；不得假定其功能、电压、接口或接入位置。")
add_ledger(ledger, "H-30", "24V水泵（1个）", "库存硬件，当前不接入水浸演示", "禁止连接建筑给水或形成循环水路；若启用，须走独立受保护电源、水电隔离和安全变更评审。")
add_ledger(ledger, "H-31", "ESP8266-01S Wi-Fi模块（2个）", "1主1备的Wi-Fi/MQTT链路", "主模块已用于USART2；备用模块替换前必须完成供电、固件、联网和重连台架验证。")
add_ledger(ledger, "H-32", "多传感器接口缺项：多通道ADC/调理、MQ加热驱动、SHT30 I²C复用或DHT22 GPIO、风机PWM/TACH、端子线束", "使六类各5个传感器与两台风机可安全接入", "未补齐前不能宣称30个传感器均可被STM32稳定采集；所有5V/12V/24V与3.3V域须分区、保险和校验。")

# 文档属性
doc.core_properties.title = "综合管廊数字孪生运维实体样品项目计划书 V3.5"
doc.core_properties.subject = "硬件数量与型号冻结"
doc.core_properties.comments = "V3.5：根据实物清单更新传感器数量、模块型号与接入边界。"
doc.save(OUTPUT)
print(OUTPUT)
