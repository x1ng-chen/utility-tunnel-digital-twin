from copy import deepcopy
from pathlib import Path

from docx import Document
from docx.enum.text import WD_BREAK


ROOT = Path(r"D:\shixi\utility-tunnel-digital-twin")
SOURCE = ROOT / "docs" / "综合管廊数字孪生运维实体样品项目计划书_V2.5.docx"
TARGET = ROOT / "docs" / "综合管廊数字孪生运维实体样品项目计划书_V2.6.docx"


def move_after(anchor, element):
    anchor._p.addnext(element)


def add_cell_row(table, values):
    cells = table.add_row().cells
    for cell, value in zip(cells, values):
        cell.text = value
    return cells


def main():
    document = Document(SOURCE)

    # Document metadata and technology decisions.
    document.tables[0].cell(1, 1).text = "V2.6（燃气管道泄漏、渗水监测与华为云部署基线版）"
    document.tables[0].cell(6, 1).text = "需求与架构基线已确认；华为云资源待创建"

    technology = document.tables[14]
    technology.cell(5, 1).text = "SQLite（本地演示）+ PostgreSQL（华为云RDS正式数据）"
    technology.cell(5, 2).text = "本地演示可离线运行；云端正式数据使用RDS PostgreSQL并保留备份恢复能力"
    technology.cell(5, 3).text = "迁移与真实连接信息在云资源创建后配置；数据库不开放公网"
    technology.cell(8, 1).text = "展示电脑本地服务 + 局域网；华为云ECS承载Web/API"
    technology.cell(8, 2).text = "本地模式保证课堂断网可演示；云端提供正式访问、数据保存与运维能力"
    technology.cell(8, 3).text = "华为云采用ECS + RDS for PostgreSQL + IoTDA；现场安全联动不依赖云端"

    milestones = document.tables[40]
    milestones.cell(1, 2).text = "需求基线、场景、尺寸、BOM、接口v0.1、采购下单；确定华为云部署基线"
    milestones.cell(3, 2).text = "ESP8266 MQTT、后端入库、WebSocket、三维映射；完成IoTDA测试接入方案与加工文件下单"

    risks = document.tables[46]
    risks.cell(11, 4).text = "变更控制；华为云基础设施可并行准备，但真机IoTDA接入不得挤占核心MVP联调时间"
    add_cell_row(
        risks,
        [
            "R13",
            "云账号、区域、权限或设备凭据未按时具备",
            "中",
            "中",
            "M0确认账号与区域；使用IAM最小权限；先保留本地演示和本地Broker回退，不把凭据提交仓库",
            "车晨星/王露帆",
        ],
    )

    deliverables = document.tables[47]
    deliverables.cell(3, 2).text = "本地Broker配置、后端、数据库迁移、Web前端、华为云部署配置与启动脚本"
    deliverables.cell(11, 2).text = "本地与华为云安装、启动、配置、备份、恢复、IoTDA接入、演示和故障处理"

    sources = document.tables[53]
    add_cell_row(
        sources,
        [
            "[17]",
            "华为云 ECS 安全组与 IoTDA 设备接入官方文档",
            "https://support.huaweicloud.com/intl/en-us/usermanual-ecs/en-us_topic_0140323157.html；https://support.huaweicloud.com/intl/en-us/devg-iothub/iot_02_0170.html",
        ],
    )

    for paragraph in document.paragraphs:
        if paragraph.text.startswith("8月27日后新增范围必须填写变更记录"):
            paragraph.text = (
                "8月27日后新增范围必须填写变更记录，包含原因、收益、工作量、对9月10日和9月30日的影响、替代项和批准人。"
                "任何影响强制场景、三维定位、真实联动或安全的变更不得口头执行。华为云基础设施可与MVP并行准备，"
                "但真机IoTDA接入、云端高级统计和非核心美化不得挤占本地闭环验收工期。"
            )
            break

    # Insert a local cloud section after section 5.2, preserving the existing plan structure.
    anchor = next(p for p in document.paragraphs if p.text == "5.2 成熟项目与GitHub复用结论")
    heading = document.add_paragraph("5.3 华为云部署与设备接入基线（2026-08-27增补）", style="Heading 2")
    intro = document.add_paragraph(
        "正式云端目标为华为云。云端用于承载Web/API、正式业务数据和设备接入；"
        "现场STM32的急停、互锁和已配置保护策略必须在网络或云端不可用时继续本地执行。"
    )
    cloud_table = document.add_table(rows=1, cols=3)
    cloud_table.style = "Table Grid"
    for cell, text in zip(cloud_table.rows[0].cells, ["层级", "华为云服务", "本项目边界"]):
        cell.text = text
    for row in [
        ("应用", "ECS + Nginx", "部署Web静态文件和后端API；公网仅提供HTTPS访问"),
        ("业务数据", "RDS for PostgreSQL", "保存资产、遥测、告警、工单、阈值和审计；仅私网TLS连接"),
        ("设备接入", "IoT Device Access（IoTDA）", "STM32/ESP8266使用MQTTS上报和接收命令；首期仅验证CTRL-01测试设备"),
        ("运维", "IAM、Cloud Eye、LTS、OBS", "最小权限、日志监控、备份和恢复演练；不在仓库保存密钥"),
    ]:
        add_cell_row(cloud_table, row)
    principles = document.add_paragraph(
        "实施约束：ECS与RDS位于同一VPC，RDS不开放公网；安全组仅开放443/TCP，"
        "22/TCP仅允许固定运维IP；PostgreSQL 5432和MQTT开发端口不得对公网开放。"
    )
    sequence = document.add_paragraph(
        "实施顺序：先确认华为云账号、区域、预算和负责人；再创建VPC、安全组、RDS与ECS；"
        "完成HTTPS、备份恢复和API健康检查后，最后在IoTDA注册CTRL-01并执行MQTTS联调。"
    )
    elements = [heading._p, intro._p, cloud_table._tbl, principles._p, sequence._p]
    for element in reversed(elements):
        move_after(anchor, element)

    document.core_properties.subject = "综合管廊数字孪生运维实体样品项目计划书 V2.6"
    document.core_properties.comments = "华为云部署与设备接入基线已同步。"
    document.save(TARGET)


if __name__ == "__main__":
    main()
