from pathlib import Path

from docx import Document


ROOT = Path(r"D:\shixi\utility-tunnel-digital-twin")
SOURCE = ROOT / "docs" / "综合管廊数字孪生运维实体样品项目计划书_V2.6.docx"
TARGET = ROOT / "docs" / "综合管廊数字孪生运维实体样品项目计划书_V2.7.docx"


def move_before(anchor, element):
    anchor._p.addprevious(element)


def add_row(table, values):
    cells = table.add_row().cells
    for cell, value in zip(cells, values):
        cell.text = value


def table_with_header(document, first_header):
    for table in document.tables:
        if table.rows and table.rows[0].cells[0].text.strip() == first_header:
            return table
    raise RuntimeError(f"table not found: {first_header}")


def table_row(table, first_cell):
    for row in table.rows:
        if row.cells[0].text.strip() == first_cell:
            return row
    raise RuntimeError(f"row not found: {first_cell}")


def paragraph(document, prefix):
    for item in document.paragraphs:
        if item.text.strip().startswith(prefix):
            return item
    raise RuntimeError(f"paragraph not found: {prefix}")


def insert_table(document, anchor, headers, rows):
    table = document.add_table(rows=1, cols=len(headers))
    table.style = "Table Grid"
    for cell, value in zip(table.rows[0].cells, headers):
        cell.text = value
    for row in rows:
        add_row(table, row)
    move_before(anchor, table._tbl)
    return table


def insert_paragraph(document, anchor, text, style=None):
    p = document.add_paragraph(text, style=style)
    move_before(anchor, p._p)
    return p


def main():
    document = Document(SOURCE)

    # Metadata and scope: V2.7 is a corrective release, not a new proposal.
    document.tables[0].cell(1, 1).text = "V2.7（工程二审修订与可验收MVP基线版）"
    document.tables[0].cell(6, 1).text = "工程二审完成；MVP范围、硬件接口、云端边界与里程碑待按本版冻结"
    for section in document.sections:
        for p in section.header.paragraphs:
            for run in p.runs:
                run.text = run.text.replace("V2.6", "V2.7")

    goals = table_with_header(document, "目标编号")
    table_row(goals, "O-02").cells[1].text = (
        "分层真实采集：MVP至少覆盖温湿度、积水/高水位和门磁或设备反馈；"
        "最终版扩展甲烷、CO、氧气与烟感。"
    )
    table_row(goals, "O-02").cells[2].text = (
        "MVP三项均通过真实台架测试；气体通道仅在专用模块完成环境基线、通信和数据质量验证后纳入最终验收。"
    )
    table_row(goals, "O-06").cells[1].text = "按门槛交付"
    table_row(goals, "O-06").cells[2].text = (
        "MVP仅在G2出口条件通过后进入平台联调；PCB或云端未通过不得阻断开发板本地闭环验收。"
    )

    decisions = table_with_header(document, "决策项")
    table_row(decisions, "泄漏与气体").cells[1].text = (
        "最终版保留甲烷、CO、烟雾和氧气；MVP不以其到货或标定作为阻塞条件。"
    )
    table_row(decisions, "泄漏与气体").cells[2].text = (
        "专用模块仅采集环境基线；异常演示只允许隔离信号模拟或合规烟感测试气雾，"
        "不得将演示等同于安全认证或教室危险气体试验。"
    )

    # Align plan to the actual repository technology stack and the cloud constraint.
    technology = table_with_header(document, "层次")
    table_row(technology, "通信").cells[1].text = "ESP8266 ESP-AT（本地MQTT）+ 本地网关转发"
    table_row(technology, "通信").cells[2].text = "STM32经UART接入本地Broker；网关负责与华为云IoTDA的安全上行。"
    table_row(technology, "通信").cells[3].text = (
        "ESP8266 ESP-AT不作为IoTDA MQTTS直连终端；如必须设备直连，改用经验证支持TLS的通信模块。"
    )
    table_row(technology, "后端").cells[1].text = "Node.js + Fastify + MQTT适配层 + WebSocket"
    table_row(technology, "后端").cells[2].text = "与当前仓库实现一致；提供鉴权、告警、工单、审计和实时推送。"
    table_row(technology, "后端").cells[3].text = "不在MVP引入微服务、集群或云端复杂规则引擎。"
    table_row(technology, "数据库").cells[1].text = "浏览器本地演示数据 + PostgreSQL（本地/API与华为云RDS）"
    table_row(technology, "数据库").cells[2].text = "与当前平台一致；PostgreSQL是正式业务数据的唯一主数据库。"
    table_row(technology, "数据库").cells[3].text = "删除SQLite正式数据表述；RDS只允许私网TLS连接。"
    table_row(technology, "前端").cells[1].text = "React + TypeScript + Vinext + Three.js"
    table_row(technology, "前端").cells[2].text = "与当前仓库实现一致，保留本地演示与API数据源切换。"
    table_row(technology, "前端").cells[3].text = "文档、部署说明和答辩材料必须同步，不再保留Vue 3表述。"
    table_row(technology, "部署").cells[1].text = "展示电脑本地服务 + 局域网；华为云ECS/RDS/IoTDA（经网关）"
    table_row(technology, "部署").cells[2].text = "断网时本地闭环可演示；云端承担远程访问、归档与运维。"
    table_row(technology, "部署").cells[3].text = "云端不参与急停、互锁和本地保护；云端接入不阻塞MVP。"

    tech_heading = paragraph(document, "5.1 技术选型")
    insert_paragraph(document, tech_heading, (
        "实施技术栈以本节技术选型表为准。图2保留为分层与数据流概念图，其中早期的Vue/Express/SQLite文字"
        "已由V2.7统一为React/Fastify/PostgreSQL，不再作为实施依据。"
    ))

    # Correct the previously added Huawei IoTDA section.
    cloud = next(table for table in document.tables if table.rows and table.rows[0].cells[0].text == "层级" and any("IoT Device Access" in c.text for r in table.rows for c in r.cells))
    table_row(cloud, "设备接入").cells[2].text = (
        "首期由展示电脑/本地网关通过MQTTS接入IoTDA；STM32+ESP8266只接入本地Broker。"
    )
    cloud_intro = paragraph(document, "正式云端目标为华为云")
    cloud_intro.text = (
        "正式云端目标为华为云。云端承载Web/API、正式业务数据和网关接入；"
        "现场STM32的急停、互锁和已配置保护策略必须在网络或云端不可用时继续本地执行。"
    )

    # Hardware inventory fixes and enforce the electrical design gate.
    bom = next(
        table for table in document.tables
        if table.rows and table.rows[0].cells[0].text.strip() == "编号"
        and any(row.cells[0].text.strip() == "H-01" for row in table.rows)
    )
    table_row(bom, "H-11").cells[0].text = "H-11"
    second_h11 = [row for row in bom.rows if row.cells[0].text.strip() == "H-11"][1]
    second_h11.cells[0].text = "H-12"
    table_row(bom, "H-15").cells[0].text = "H-15"

    inventory = table_with_header(document, "资产")
    table_row(inventory, "H-03").cells[1].text = "1.44寸ST7735S TFT显示屏（实物接口：GND/VCC/SCL/SDA/RES/DC/CS/BLK）"
    table_row(inventory, "H-03").cells[3].text = "按实物确认驱动芯片、VCC、背光与初始化参数；当前固件为软件SPI，最终PCB评估硬件SPI。"
    table_row(inventory, "H-12").cells[0].text = "H-25"

    hardware_anchor = paragraph(document, "8 嵌入式软件设计")
    insert_paragraph(document, hardware_anchor, "7.4 工程二审后的硬件冻结门槛", "Heading 2")
    insert_paragraph(document, hardware_anchor, (
        "未完成下表核验的模块不得接入最终PCB；所有电压、电流和有效电平均以实物数据手册与台架实测为准。"
    ))
    insert_table(document, hardware_anchor,
        ["对象", "必须冻结的设计", "禁止的做法", "验收证据"],
        [
            ("SWD/启动", "Serial Wire、SWDIO/SWCLK/NRST/GND/3.3V、BOOT0下拉与复位电路", "设置No Debug或仅保留串口下载", "ST-Link连续下载、复位和断点调试记录"),
            ("ESP8266", "独立3.3V稳压、峰值电流余量、EN/RST/启动脚定义、USART2 DMA", "由开发板弱3.3V口直接假定供电足够", "联网、掉电、重连和电压记录"),
            ("WS2812B", "74AHCT/74HCT电平转换、数据串阻、5V去耦与共地", "3.3V数据直推5V灯带作为正式设计", "最长灯带全亮及报警色测试"),
            ("风机/继电器/蜂鸣器", "MOSFET或经验证驱动、续流/TVS、独立负载电源、反馈接口", "MCU GPIO直驱负载或未核验5V触发", "空载、带载、急停和故障反馈记录"),
            ("水浸/烟感/外部输入", "浮球冗余、光耦隔离、上拉、去抖、端子和线缆标签", "12V或外部干接点直连MCU", "正常、触发、断线和短接测试"),
            ("RS485气体模块", "3.3V收发器、地址表、供电/预热要求、终端与保护策略", "未取得数据手册即画板或用MQ模块作定量结论", "环境基线、通信、离线与模拟盒隔离测试"),
        ])

    # Make software architecture and scope executable.
    sw_anchor = paragraph(document, "9 通信、数据模型与接口")
    insert_paragraph(document, sw_anchor, "8.4 调度、状态机与故障处理修订", "Heading 2")
    insert_paragraph(document, sw_anchor, (
        "本期采用裸机+中断+周期调度+显式状态机，不引入FreeRTOS。中断仅记录事件或写入轻量队列；"
        "显示、传感器解析、MQTT和控制决策均在主循环任务中执行。只有在MVP已稳定且新增任务确有实时隔离需求时再评估RTOS。"
    ))
    insert_table(document, sw_anchor,
        ["职责", "必须实现", "验收重点"],
        [
            ("数据质量", "每个测点携带valid/stale/fault/simulated状态、采样时间和序列号", "平台不将故障、过期或模拟值误显示为正常真实数据"),
            ("安全状态机", "NORMAL、PREALARM、ALARM、INTERLOCK、FAULT、EMERGENCY与恢复条件", "云端命令不得绕过急停、互锁、水位高高保护"),
            ("通信", "ESP-AT非阻塞状态机、重连、心跳、cmdId去重、命令过期和回执", "重复QoS 1命令不重复动作；断网本地联动持续"),
            ("参数保存", "双记录、版本、CRC与最小写入间隔", "掉电后阈值可恢复；不频繁擦写内部Flash"),
            ("故障恢复", "IWDG仅在关键任务健康时喂狗；记录复位原因与模块离线原因", "人为制造卡死/断线后系统可进入可解释安全状态"),
        ])

    # New gate-based delivery schedule replaces optimistic date-first milestones.
    milestones = table_with_header(document, "日期")
    schedule = [
        ("8/27-8/31", "G0 设计冻结", "MVP三场景、真实技术栈、BOM、引脚表、供电表、云网关边界和采购清单冻结", "全员"),
        ("9/1-9/7", "G1 单模块台架", "传感器、执行器、驱动、电源完成正常/异常/断线测试；ST-Link调试链路可用", "王为/闵昊/胡雨皓"),
        ("9/8-9/14", "G2 本地闭环MVP", "三场景在断网条件下完成采集、报警、联动、恢复；开发板为可验收主链路", "闵昊/王为"),
        ("9/8-9/20", "G3 平台与实体联调", "STM32→本地MQTT→Fastify/PostgreSQL→React/三维→工单→回执真实贯通", "王露帆/闵昊"),
        ("9/1-9/20", "G4 PCB/实体并行", "原理图双评审、首板、焊接和上电；失败时不影响开发板MVP", "王为"),
        ("9/21-9/24", "G5 云端网关验证", "网关到华为云IoTDA完成一台设备安全上行、回执和本地回退验证", "王露帆/闵昊"),
        ("9/25-9/27", "G6 回归与稳定性", "三场景连续三次、断网恢复、急停和稳定性测试；关键缺陷关闭", "胡雨皓/全员"),
        ("9/28-9/30", "最终交付", "演示、答辩材料、测试证据、图纸、部署和归档会签", "车晨星/全员"),
    ]
    for row, values in zip(milestones.rows[1:], schedule):
        for cell, value in zip(row.cells, values):
            cell.text = value
    while len(milestones.rows) > len(schedule) + 1:
        milestones._tbl.remove(milestones.rows[-1]._tr)

    mvp_heading = paragraph(document, "15.2 9月10日MVP最小范围")
    mvp_items = []
    started = False
    for item in document.paragraphs:
        if item == mvp_heading:
            started = True
            continue
        if started and item.text.startswith("15.3 "):
            break
        if started and item.text.strip():
            mvp_items.append(item)
    for item, text in zip(mvp_items[:5], [
        "实体台架完成温湿度、积水/高水位、门磁或设备反馈三类MVP测点；气体通道不作为MVP阻塞项。",
        "STM32在断网状态下完成本地报警、联动、恢复；急停和高水位保护不依赖云端。",
        "STM32→ESP8266→本地Mosquitto→Fastify/PostgreSQL→React→三维→工单完成真实链路运行。",
        "积水/高水位、温湿度异常和门磁或设备反馈三个场景完成定位、报警、联动、确认、工单、恢复和关闭。",
        "每个MVP场景可在开发板链路连续演示3次；PCB或云端未完成时不影响本地闭环验收。",
    ]):
        item.text = text
    mvp_replacements = {
        "实体台架已能真实读取甲烷、CO、氧气、温度、水浸/水位和至少一个设备反馈。": "实体台架完成温湿度、积水/高水位、门磁或设备反馈三类MVP测点；气体通道不作为MVP阻塞项。",
        "已能真实控制风机、照明和声光报警中的核心设备。": "STM32在断网状态下完成本地报警、联动、恢复；急停和高水位保护不依赖云端。",
        "STM32→ESP8266→Mosquitto→后端→数据库→Web→三维完整链路运行。": "STM32→ESP8266→本地Mosquitto→Fastify/PostgreSQL→React→三维→工单完成真实链路运行。",
        "燃气管道泄漏和管廊渗水/积水两个强制场景完成三维定位、报警、联动、确认、工单、恢复和关闭。": "积水/高水位、温湿度异常和门磁或设备反馈三个场景完成定位、报警、联动、确认、工单、恢复和关闭。",
        "即使最终外壳或PCB尚未完成，MVP必须在可靠台架上可重复演示三次。": "每个MVP场景可在开发板链路连续演示3次；PCB或云端未完成时不影响本地闭环验收。",
    }
    for item in document.paragraphs:
        if item.text in mvp_replacements:
            item.text = mvp_replacements[item.text]

    # Add explicit traceable tests before the existing evidence section.
    test_anchor = paragraph(document, "16.4 验收证据")
    insert_paragraph(document, test_anchor, "16.3 工程二审补充验收矩阵", "Heading 2")
    insert_table(document, test_anchor,
        ["功能", "实现方式", "测试方法", "量化指标/验收标准"],
        [
            ("本地安全闭环", "STM32状态机与硬件急停", "断开网络后分别触发MVP三场景", "每场景连续3次成功；本地报警与联动不中断"),
            ("水浸保护", "水探针+浮球双通道", "受控滴水，分别触发探头和浮球", "滴水量、响应时间与恢复时间【需按实物确认】；高水位独立触发保护"),
            ("风机运行", "使能/PWM+转速或INA219反馈", "断开反馈或模拟卡转", "命令开启后无有效反馈必须生成故障；有效阈值【需按风机规格确认】"),
            ("通信可靠性", "本地MQTT、cmdId、重连与回执", "断网、恢复、同cmdId重复投递、超时", "本地功能不中断；重连时间【建议≤15秒，需确认】；重复命令不得重复执行"),
            ("三维定位", "资产编码、nodeId、GLB网格映射", "逐一触发关键资产", "关键资产100%定位正确；记录资产清单与截图"),
            ("稳定性", "版本冻结后长时运行", "记录采样数、丢失数、崩溃数和日志", "连续运行时长、丢失率与延迟【需确定测量方法后确认】"),
            ("云端网关", "本地网关MQTTS接入IoTDA", "一台CTRL-01完成上行、命令和断网回退", "凭据不入库；云端不可用时本地闭环仍通过"),
        ])

    risks = next(
        table for table in document.tables
        if table.rows and table.rows[0].cells[0].text.strip() == "编号"
        and any(row.cells[0].text.strip() == "R1" for row in table.rows)
    )
    add_row(risks, [
        "R14", "ESP8266与IoTDA MQTTS直接接入不兼容", "高", "高",
        "固定为本地网关转发；若改为直连，必须更换并台架验证支持TLS的通信模块", "王露帆/闵昊"
    ])
    add_row(risks, [
        "R15", "开发板调试接口被复用配置关闭", "中", "高",
        "SYS固定Serial Wire；PCB保留SWD/NRST/BOOT0；每次CubeMX改动后复测ST-Link", "闵昊/王为"
    ])

    # Visible revision record: makes review decisions traceable to implementation.
    anchor = paragraph(document, "6 实体样品设计")
    insert_paragraph(document, anchor, "5.4 工程二审修订记录（V2.7）", "Heading 2")
    insert_table(document, anchor,
        ["级别", "原问题", "本版修订", "原因"],
        [
            ("P0", "ESP8266被规划为IoTDA MQTTS直连终端", "改为本地Broker+网关转发；直连需替换模块", "ESP8266 ESP-AT TLS能力不满足该路径"),
            ("P0", "No Debug配置会关闭SWD", "固定Serial Wire及SWD/NRST/BOOT0硬件门槛", "保障ST-Link下载、断点与故障定位"),
            ("P0", "计划书与仓库技术栈不一致", "统一为React、Fastify、PostgreSQL", "使文档、代码、部署与答辩口径一致"),
            ("P1", "七场景同时作为关键路径", "MVP收敛为三场景，气体等进入最终扩展", "降低采购、标定和安全约束对交付的阻塞"),
            ("P1", "执行器只有控制、无运行证据", "风机增加转速或电流反馈；验收采用反馈闭环", "证明实际执行而非仅GPIO输出"),
        ])

    document.core_properties.subject = "综合管廊数字孪生运维实体样品项目计划书 V2.7"
    document.core_properties.comments = "V2.7：依据工程二审修正MVP、接口、电源与云端接入边界。"
    document.save(TARGET)


if __name__ == "__main__":
    main()
