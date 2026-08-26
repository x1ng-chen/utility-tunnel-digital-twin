from __future__ import annotations

from pathlib import Path
from datetime import date
from typing import Iterable, Sequence

from PIL import Image, ImageDraw, ImageFont
from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.style import WD_STYLE_TYPE
from docx.enum.table import WD_ALIGN_VERTICAL, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Inches, Pt, RGBColor


ROOT = Path(r"D:\实习")
ASSET_DIR = ROOT / "_plan_v2_assets"
OUTPUT = ROOT / "综合管廊数字孪生运维实体样品项目计划书_V2.5_燃气管道泄漏与渗水监测版.docx"
ASSET_DIR.mkdir(parents=True, exist_ok=True)


# Design preset: standard_business_brief.
# Named override CJK-Legibility: East Asian text uses Microsoft YaHei while
# Latin characters keep Calibri. Named override Project-Plan-Density: selected
# large lookup tables may use 8.5-9 pt text without changing body typography.
BLUE = "2E74B5"
DARK_BLUE = "1F4D78"
NAVY = "0B2545"
MUTED = "5B6573"
LIGHT_GRAY = "F2F4F7"
BLUE_GRAY = "E8EEF5"
CALLOUT = "F4F6F9"
GREEN = "DDEBF7"
AMBER = "FFF2CC"
RED = "FCE4D6"
WHITE = "FFFFFF"
BLACK = "111111"
TOTAL_DXA = 9360
TABLE_INDENT = 120


def rgb(hex_color: str) -> RGBColor:
    return RGBColor.from_string(hex_color)


def set_run_font(run, size=11, bold=None, color=BLACK, italic=None, mono=False):
    latin = "Consolas" if mono else "Calibri"
    east = "Microsoft YaHei"
    run.font.name = latin
    run._element.get_or_add_rPr().rFonts.set(qn("w:ascii"), latin)
    run._element.get_or_add_rPr().rFonts.set(qn("w:hAnsi"), latin)
    run._element.get_or_add_rPr().rFonts.set(qn("w:eastAsia"), east)
    run.font.size = Pt(size)
    run.font.color.rgb = rgb(color)
    if bold is not None:
        run.bold = bold
    if italic is not None:
        run.italic = italic


def shade_cell(cell, fill: str):
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = tc_pr.find(qn("w:shd"))
    if shd is None:
        shd = OxmlElement("w:shd")
        tc_pr.append(shd)
    shd.set(qn("w:fill"), fill)


def cell_margins(cell, top=80, start=120, bottom=80, end=120):
    tc = cell._tc
    tc_pr = tc.get_or_add_tcPr()
    tc_mar = tc_pr.first_child_found_in("w:tcMar")
    if tc_mar is None:
        tc_mar = OxmlElement("w:tcMar")
        tc_pr.append(tc_mar)
    for margin, value in (("top", top), ("start", start), ("bottom", bottom), ("end", end)):
        node = tc_mar.find(qn(f"w:{margin}"))
        if node is None:
            node = OxmlElement(f"w:{margin}")
            tc_mar.append(node)
        node.set(qn("w:w"), str(value))
        node.set(qn("w:type"), "dxa")


def set_repeat_table_header(row):
    tr_pr = row._tr.get_or_add_trPr()
    tbl_header = OxmlElement("w:tblHeader")
    tbl_header.set(qn("w:val"), "true")
    tr_pr.append(tbl_header)


def set_row_cant_split(row):
    tr_pr = row._tr.get_or_add_trPr()
    node = tr_pr.find(qn("w:cantSplit"))
    if node is None:
        node = OxmlElement("w:cantSplit")
        node.set(qn("w:val"), "true")
        tr_pr.append(node)


def set_table_geometry(table, widths: Sequence[int]):
    assert sum(widths) == TOTAL_DXA, (widths, sum(widths))
    table.alignment = WD_TABLE_ALIGNMENT.LEFT
    table.autofit = False
    tbl_pr = table._tbl.tblPr
    layout = tbl_pr.find(qn("w:tblLayout"))
    if layout is None:
        layout = OxmlElement("w:tblLayout")
        tbl_pr.append(layout)
    layout.set(qn("w:type"), "fixed")

    tbl_w = tbl_pr.find(qn("w:tblW"))
    if tbl_w is None:
        tbl_w = OxmlElement("w:tblW")
        tbl_pr.append(tbl_w)
    tbl_w.set(qn("w:w"), str(TOTAL_DXA))
    tbl_w.set(qn("w:type"), "dxa")

    tbl_ind = tbl_pr.find(qn("w:tblInd"))
    if tbl_ind is None:
        tbl_ind = OxmlElement("w:tblInd")
        tbl_pr.append(tbl_ind)
    tbl_ind.set(qn("w:w"), str(TABLE_INDENT))
    tbl_ind.set(qn("w:type"), "dxa")

    grid = table._tbl.tblGrid
    for child in list(grid):
        grid.remove(child)
    for width in widths:
        col = OxmlElement("w:gridCol")
        col.set(qn("w:w"), str(width))
        grid.append(col)

    for row in table.rows:
        for idx, cell in enumerate(row.cells):
            width = widths[min(idx, len(widths) - 1)]
            tc_pr = cell._tc.get_or_add_tcPr()
            tc_w = tc_pr.find(qn("w:tcW"))
            if tc_w is None:
                tc_w = OxmlElement("w:tcW")
                tc_pr.append(tc_w)
            tc_w.set(qn("w:w"), str(width))
            tc_w.set(qn("w:type"), "dxa")
            cell.width = Inches(width / 1440)
            cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
            cell_margins(cell)


def set_cell_text(cell, text, bold=False, size=9.2, color=BLACK, align=WD_ALIGN_PARAGRAPH.LEFT):
    cell.text = ""
    p = cell.paragraphs[0]
    p.alignment = align
    p.paragraph_format.space_before = Pt(0)
    p.paragraph_format.space_after = Pt(0)
    p.paragraph_format.line_spacing = 1.08
    run = p.add_run(str(text))
    set_run_font(run, size=size, bold=bold, color=color)


def add_table(doc, headers: Sequence[str], rows: Iterable[Sequence[str]], widths: Sequence[int], font_size=9.2):
    table = doc.add_table(rows=1, cols=len(headers))
    table.style = "Table Grid"
    for i, h in enumerate(headers):
        set_cell_text(table.rows[0].cells[i], h, bold=True, size=font_size, color=NAVY,
                      align=WD_ALIGN_PARAGRAPH.CENTER)
        shade_cell(table.rows[0].cells[i], LIGHT_GRAY)
    set_repeat_table_header(table.rows[0])
    set_row_cant_split(table.rows[0])
    for row_values in rows:
        row = table.add_row()
        for i, value in enumerate(row_values):
            align = WD_ALIGN_PARAGRAPH.CENTER if i == 0 and len(headers) > 2 else WD_ALIGN_PARAGRAPH.LEFT
            set_cell_text(row.cells[i], value, size=font_size, align=align)
        set_row_cant_split(row)
    set_table_geometry(table, widths)
    p = doc.add_paragraph()
    p.paragraph_format.space_after = Pt(2)
    return table


def add_body(doc, text, bold_prefix=None, align=WD_ALIGN_PARAGRAPH.JUSTIFY, after=6):
    p = doc.add_paragraph()
    p.alignment = align
    p.paragraph_format.space_before = Pt(0)
    p.paragraph_format.space_after = Pt(after)
    p.paragraph_format.line_spacing = 1.10
    if bold_prefix and text.startswith(bold_prefix):
        r1 = p.add_run(bold_prefix)
        set_run_font(r1, bold=True, color=NAVY)
        r2 = p.add_run(text[len(bold_prefix):])
        set_run_font(r2)
    else:
        r = p.add_run(text)
        set_run_font(r)
    return p


def add_bullets(doc, items: Iterable[str], level=0):
    for item in items:
        p = doc.add_paragraph(style="List Bullet" if level == 0 else "List Bullet 2")
        p.paragraph_format.space_after = Pt(4)
        p.paragraph_format.line_spacing = 1.167
        r = p.add_run(item)
        set_run_font(r)


def add_numbers(doc, items: Iterable[str]):
    for item in items:
        p = doc.add_paragraph(style="List Number")
        p.paragraph_format.space_after = Pt(4)
        p.paragraph_format.line_spacing = 1.167
        r = p.add_run(item)
        set_run_font(r)


def add_callout(doc, label: str, text: str, fill=CALLOUT, color=NAVY):
    table = doc.add_table(rows=1, cols=1)
    table.style = "Table Grid"
    set_table_geometry(table, [TOTAL_DXA])
    shade_cell(table.cell(0, 0), fill)
    p = table.cell(0, 0).paragraphs[0]
    p.paragraph_format.space_after = Pt(0)
    r = p.add_run(f"{label}：")
    set_run_font(r, bold=True, color=color)
    r = p.add_run(text)
    set_run_font(r, color=BLACK)
    doc.add_paragraph().paragraph_format.space_after = Pt(2)


def add_code(doc, text: str):
    table = doc.add_table(rows=1, cols=1)
    table.style = "Table Grid"
    set_table_geometry(table, [TOTAL_DXA])
    shade_cell(table.cell(0, 0), "F7F8FA")
    p = table.cell(0, 0).paragraphs[0]
    p.paragraph_format.space_after = Pt(0)
    for idx, line in enumerate(text.splitlines()):
        if idx:
            p.add_run().add_break()
        r = p.add_run(line)
        set_run_font(r, size=8.7, mono=True, color="263238")
    doc.add_paragraph().paragraph_format.space_after = Pt(2)


def add_heading(doc, text: str, level: int, page_break=False):
    p = doc.add_paragraph(style=f"Heading {level}")
    # Project plans contain many multi-page lookup tables.  A hard page break
    # before every chapter can strand one or two continuation rows on an
    # otherwise empty page.  Keep headings with their first content block and
    # let Word paginate naturally instead.
    p.paragraph_format.keep_with_next = True
    r = p.add_run(text)
    set_run_font(r, size={1: 16, 2: 13, 3: 12}[level], bold=True,
                 color=BLUE if level < 3 else DARK_BLUE)
    return p


def add_caption(doc, text: str):
    p = doc.add_paragraph(style="Caption")
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(3)
    p.paragraph_format.space_after = Pt(8)
    r = p.add_run(text)
    set_run_font(r, size=9, color=MUTED)


def set_alt_text(inline_shape, title, description):
    doc_pr = inline_shape._inline.docPr
    doc_pr.set("title", title)
    doc_pr.set("descr", description)


def font(size, bold=False):
    path = r"C:\Windows\Fonts\msyhbd.ttc" if bold else r"C:\Windows\Fonts\msyh.ttc"
    return ImageFont.truetype(path, size)


def draw_arrow(draw, start, end, color="#55708D", width=5):
    draw.line([start, end], fill=color, width=width)
    x2, y2 = end
    x1, y1 = start
    import math
    ang = math.atan2(y2-y1, x2-x1)
    for off in (2.55, -2.55):
        px = x2 + 18 * math.cos(ang + off)
        py = y2 + 18 * math.sin(ang + off)
        draw.line([(x2, y2), (px, py)], fill=color, width=width)


def architecture_diagram(path: Path):
    im = Image.new("RGB", (1500, 950), "white")
    d = ImageDraw.Draw(im)
    title = "综合管廊实体样品与Web数字孪生总体架构"
    d.text((750, 45), title, anchor="ma", font=font(38, True), fill="#0B2545")
    bands = [
        ("现场层", "甲烷 / CO / 烟雾 / 氧气 / 温湿度 / 水浸与水位 / 门磁 / 温度 / 风机转速", "#E8F1FA"),
        ("控制层", "STM32F103RCT6：采集、滤波、阈值判断、联动控制、故障保护", "#DDEBF7"),
        ("通信层", "ESP8266（ESP-AT） + MQTT 3.1.1；USB串口作为离线调试后备", "#E2F0D9"),
        ("平台层", "Mosquitto + Node.js/Express + SQLite + WebSocket；本地电脑部署", "#FFF2CC"),
        ("应用层", "Vue 3 + Three.js：三维定位、报警、控制、工单、历史、统计", "#FCE4D6"),
    ]
    y = 130
    boxes = []
    for name, desc, fill in bands:
        box = (140, y, 1360, y + 120)
        d.rounded_rectangle(box, radius=18, fill=fill, outline="#55708D", width=3)
        d.text((190, y+60), name, anchor="lm", font=font(30, True), fill="#1F4D78")
        d.text((390, y+60), desc, anchor="lm", font=font(25), fill="#263238")
        boxes.append(box)
        y += 150
    for i in range(len(boxes)-1):
        draw_arrow(d, (750, boxes[i][3]+4), (750, boxes[i+1][1]-6))
    im.save(path, quality=95)


def workflow_diagram(path: Path):
    im = Image.new("RGB", (1600, 900), "white")
    d = ImageDraw.Draw(im)
    d.text((800, 45), "完整运维闭环", anchor="ma", font=font(40, True), fill="#0B2545")
    labels = ["实时监测", "异常判定", "三维定位", "设备联动", "告警确认", "生成工单", "现场处置", "恢复复核", "关闭归档"]
    coords = [(100,180),(410,180),(720,180),(1030,180),(1190,420),(880,620),(570,620),(260,620),(100,420)]
    boxes=[]
    for i,(x,y) in enumerate(coords):
        w,h=230,95
        fill = "#E8EEF5" if i<4 else ("#FFF2CC" if i<7 else "#E2F0D9")
        d.rounded_rectangle((x,y,x+w,y+h), radius=16, fill=fill, outline="#55708D", width=3)
        d.text((x+w/2,y+h/2), labels[i], anchor="mm", font=font(26, True), fill="#1F4D78")
        boxes.append((x,y,x+w,y+h))
    for i in range(len(boxes)):
        a=boxes[i]; b=boxes[(i+1)%len(boxes)]
        ax=(a[0]+a[2])/2; ay=(a[1]+a[3])/2
        bx=(b[0]+b[2])/2; by=(b[1]+b[3])/2
        import math
        dx,dy=bx-ax,by-ay
        l=max(math.hypot(dx,dy),1)
        ux,uy=dx/l,dy/l
        start=(ax+ux*120,ay+uy*52)
        end=(bx-ux*120,by-uy*52)
        draw_arrow(d,start,end)
    d.text((800,805), "每个事件必须保留时间、位置、测点值、联动结果、操作人和关闭结论", anchor="mm", font=font(24), fill="#5B6573")
    im.save(path, quality=95)


def model_diagram(path: Path):
    im = Image.new("RGB", (1600, 900), "white")
    d = ImageDraw.Draw(im)
    d.text((800, 45), "实体样品建议布局（俯视示意）", anchor="ma", font=font(38, True), fill="#0B2545")
    outer=(120,150,1480,700)
    d.rounded_rectangle(outer, radius=20, fill="#F7F8FA", outline="#1F4D78", width=5)
    zone_w=(outer[2]-outer[0])/3
    colors=["#E8EEF5","#E2F0D9","#FFF2CC"]
    for i,name in enumerate(["A区：入口与环境", "B区：干燥管廊与积水监测", "C区：气体与设备"]):
        x0=outer[0]+i*zone_w; x1=x0+zone_w
        d.rectangle((x0,outer[1],x1,outer[3]), fill=colors[i], outline="#55708D", width=2)
        d.text(((x0+x1)/2,185), name, anchor="ma", font=font(25,True), fill="#1F4D78")
    # pipes / cable trays
    d.line((180,310,1420,310), fill="#727D8A", width=24)
    d.text((800,280), "干燥管廊管线 / 少量滴水演示点", anchor="ms", font=font(20), fill="#3A3A3A")
    d.line((180,470,1420,470), fill="#B5651D", width=20)
    d.text((800,440), "多气体监测安装区（无气体释放）", anchor="ms", font=font(20), fill="#7A3E00")
    d.line((180,590,1420,590), fill="#5A5A5A", width=16)
    d.text((800,560), "模拟电缆桥架与分区照明", anchor="ms", font=font(20), fill="#3A3A3A")
    items=[(230,390,"门磁/温湿度"),(640,390,"水浸/高水位"),(1120,390,"CH₄/CO/O₂/烟雾/风机"),(1320,645,"控制箱")]
    for x,y,t in items:
        d.ellipse((x-13,y-13,x+13,y+13),fill="#C62828")
        d.text((x+22,y),t,anchor="lm",font=font(19,True),fill="#263238")
    d.text((800,785), "总尺寸约 1400 × 650 × 550 mm；两段式底座，透明罩可拆，内部仅使用12V/5V/3.3V直流", anchor="mm", font=font(23), fill="#5B6573")
    im.save(path, quality=95)


def configure_document(doc: Document):
    section = doc.sections[0]
    section.page_width = Inches(8.5)
    section.page_height = Inches(11)
    section.top_margin = Inches(1)
    section.bottom_margin = Inches(1)
    section.left_margin = Inches(1)
    section.right_margin = Inches(1)
    section.header_distance = Inches(0.492)
    section.footer_distance = Inches(0.492)
    section.different_first_page_header_footer = True

    styles = doc.styles
    normal = styles["Normal"]
    normal.font.name = "Calibri"
    normal._element.rPr.rFonts.set(qn("w:eastAsia"), "Microsoft YaHei")
    normal.font.size = Pt(11)
    normal.paragraph_format.space_after = Pt(6)
    normal.paragraph_format.line_spacing = 1.10

    settings = {
        "Heading 1": (16, BLUE, 16, 8),
        "Heading 2": (13, BLUE, 12, 6),
        "Heading 3": (12, DARK_BLUE, 8, 4),
    }
    for name, (size, color, before, after) in settings.items():
        st = styles[name]
        st.font.name = "Calibri"
        st._element.rPr.rFonts.set(qn("w:eastAsia"), "Microsoft YaHei")
        st.font.size = Pt(size)
        st.font.bold = True
        st.font.color.rgb = rgb(color)
        st.paragraph_format.space_before = Pt(before)
        st.paragraph_format.space_after = Pt(after)
        st.paragraph_format.keep_with_next = True

    for name, left, hanging in (("List Bullet", 0.5, 0.25), ("List Number", 0.5, 0.25), ("List Bullet 2", 0.75, 0.25)):
        st = styles[name]
        st.font.name = "Calibri"
        st._element.rPr.rFonts.set(qn("w:eastAsia"), "Microsoft YaHei")
        st.font.size = Pt(11)
        st.paragraph_format.left_indent = Inches(left)
        st.paragraph_format.first_line_indent = Inches(-hanging)
        st.paragraph_format.space_after = Pt(4)
        st.paragraph_format.line_spacing = 1.167

    caption = styles["Caption"]
    caption.font.name = "Calibri"
    caption._element.rPr.rFonts.set(qn("w:eastAsia"), "Microsoft YaHei")
    caption.font.size = Pt(9)
    caption.font.color.rgb = rgb(MUTED)

    # Quiet running header and footer on subsequent pages.
    hp = section.header.paragraphs[0]
    hp.alignment = WD_ALIGN_PARAGRAPH.LEFT
    r = hp.add_run("综合管廊数字孪生运维实体样品 | 项目计划书 V2.5")
    set_run_font(r, size=8.5, color=MUTED)
    fp = section.footer.paragraphs[0]
    fp.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    r = fp.add_run("第 ")
    set_run_font(r, size=8.5, color=MUTED)
    fld = OxmlElement("w:fldSimple")
    fld.set(qn("w:instr"), "PAGE")
    fp._p.append(fld)
    r = fp.add_run(" 页")
    set_run_font(r, size=8.5, color=MUTED)

    cp = doc.core_properties
    cp.title = "综合管廊数字孪生运维实体样品项目计划书"
    cp.subject = "实体样品、STM32控制、真实传感、Web三维与完整运维流程"
    cp.author = "综合管廊项目组"
    cp.keywords = "综合管廊, STM32, 数字孪生, 物联网, 三维可视化, 运维"


def cover(doc):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(82)
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = p.add_run("项目计划书")
    set_run_font(r, size=13, bold=True, color=BLUE)
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(18)
    p.paragraph_format.space_after = Pt(10)
    r = p.add_run("综合管廊数字孪生运维实体样品")
    set_run_font(r, size=28, bold=True, color=NAVY)
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_after = Pt(36)
    r = p.add_run("真实传感 · STM32控制 · Web三维定位 · 运维闭环")
    set_run_font(r, size=14, color=MUTED)
    add_table(doc, ["文档属性", "内容"], [
        ("版本", "V2.5（燃气管道泄漏与渗水监测版）"),
        ("计划周期", "2026年8月25日 - 2026年9月30日"),
        ("阶段目标", "9月10日前完成主要功能；9月30日前完成全部交付"),
        ("项目范围", "仅负责综合管廊模块，不扩展至其他独立管网模块"),
        ("团队规模", "6人，岗位保持不变"),
        ("文档状态", "需求基线已确认，可进入实施"),
    ], [2300, 7060], font_size=10)
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(38)
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = p.add_run("编制日期：2026年8月25日")
    set_run_font(r, size=10, color=MUTED)
    doc.add_page_break()


def build():
    arch = ASSET_DIR / "architecture.png"
    flow = ASSET_DIR / "workflow.png"
    model = ASSET_DIR / "model_layout.png"
    architecture_diagram(arch)
    workflow_diagram(flow)
    model_diagram(model)

    doc = Document()
    configure_document(doc)
    cover(doc)

    add_heading(doc, "文档控制与决策基线", 1)
    add_callout(doc, "已确认方向", "只建设综合管廊模块；采用真实传感器和真实控制设备；STM32F103RCT6为现场主控；Web端建立与实体一一映射的三维模型；教室可联网，但系统核心功能须支持局域网独立运行；所有列明交付物均纳入最终范围。")
    add_table(doc, ["决策项", "已确认内容", "实施含义"], [
        ("业务目标", "完整的管廊运维流程", "不能只做数据大屏，必须形成监测、报警、联动、工单、处置、复核、归档闭环"),
        ("实体展示", "教室桌面展示，由方案统一把控", "优先考虑运输、透明可视、低压安全、模块化装配和故障复现"),
        ("采集与控制", "真实信息、真实设备", "传感器、风机、照明和声光报警接入现场控制器；水浸场景由少量受控滴水触发"),
        ("泄漏与气体", "必须具备", "保留干燥管廊外部渗水/积水演示；设置燃气管道预设裂缝点，监测甲烷、CO、烟雾和氧气，异常场景采用受控信号模拟，不在教室释放危险气体"),
        ("主控", "STM32F103RCT6", "原型期使用现成开发板；冻结接口后制作并焊接定制接口PCB"),
        ("三维", "Web端三维准确定位", "实体、测点、设备、模型网格统一编码，告警时自动聚焦和变色"),
        ("时间", "9月10日主要功能，9月30日全部完成", "采用双基线：MVP基线和最终验收基线"),
        ("预算", "以正常完成为原则", "不采购制作工具；零部件按可靠性和交付期选择，设置15%备件及浮动"),
    ], [1800, 3200, 4360], font_size=8.8)
    add_heading(doc, "章节索引", 2)
    add_table(doc, ["章节", "内容"], [
        ("1-3", "项目定义、范围、完整运维流程"),
        ("4-6", "需求分析、总体架构、实体样品"),
        ("7-10", "硬件、嵌入式、通信数据、Web三维"),
        ("11-14", "平台、报警联动、安全、团队分工"),
        ("15-18", "进度、测试验收、预算采购、风险"),
        ("19及附录", "交付、仓库规范、I/O、MQTT、场景脚本、资料来源"),
    ], [1500, 7860], font_size=9.5)

    add_heading(doc, "1 项目定义", 1, page_break=True)
    add_heading(doc, "1.1 项目愿景", 2)
    add_body(doc, "建设一套可在教室稳定运行的综合管廊数字孪生运维实体样品。实体部分真实感知环境与设备状态并执行联动控制；软件部分接收现场数据，在Web三维模型中准确定位异常设备和区域，驱动报警、运维工单、处置复核和历史分析，最终形成可重复演示、可测试、可部署、可继续扩展的完整系统。")
    add_heading(doc, "1.2 可量化目标", 2)
    add_table(doc, ["目标编号", "目标", "验收指标"], [
        ("O-01", "实体与三维一致", "所有关键设备、传感器和区域具备唯一编码；报警点能够自动聚焦到对应三维对象"),
        ("O-02", "真实采集", "至少覆盖温度、湿度、甲烷、CO、烟雾、氧气、积水/水位、门磁和设备运行状态"),
        ("O-03", "真实控制", "能够控制风机、照明和声光报警，并返回执行结果；水浸场景不引入循环水控制设备"),
        ("O-04", "完整运维", "异常事件从产生到关闭均留痕，具有确认人、工单、处置记录、复核值和关闭时间"),
        ("O-05", "稳定运行", "局域网连续运行4小时无崩溃；关键告警/控制消息不因页面刷新丢失"),
        ("O-06", "按期交付", "9月10日前通过MVP验收；9月30日前完成最终验收和全部文档"),
    ], [1200, 2600, 5560], font_size=9)
    add_heading(doc, "1.3 项目成功定义", 2)
    add_bullets(doc, [
        "演示人员无需修改代码，即可通过安全操作触发管廊渗水/积水、燃气管道泄漏、温度异常、烟雾、门禁和设备故障场景。",
        "Web端在单一界面完成三维定位、数据查看、报警确认、联动状态查看、工单流转和恢复关闭。",
        "断网时局域网仍能运行；联网仅用于后续远程访问或备份，不构成核心依赖。",
        "项目可复现：新电脑按照部署手册能启动系统，新成员按照接线图和BOM能够完成维护。",
    ])

    add_heading(doc, "2 项目范围与边界", 1, page_break=True)
    add_heading(doc, "2.1 本期范围", 2)
    add_table(doc, ["工作域", "纳入内容"], [
        ("实体结构", "综合管廊舱体、管线支架、少量滴水演示点与接水盘、多气体监测安装位、设备节点、照明、检修口和控制箱"),
        ("现场控制", "STM32采集、滤波、阈值、状态机、联动、命令校验、故障保护、通信和日志"),
        ("平台软件", "MQTT接入、实时数据、设备台账、报警、工单、控制、历史曲线、审计日志和配置"),
        ("数字孪生", "Web三维模型、对象编码映射、状态着色、告警定位、设备弹窗、联动动画和视角导航"),
        ("运维流程", "监测、预警、报警、确认、派单、处置、复核、关闭、查询和统计"),
        ("工程化", "PCB接口板、接线图、BOM、部署、测试、演示脚本、视频、源代码和完整文档"),
    ], [2100, 7260], font_size=9.3)
    add_heading(doc, "2.2 明确不纳入", 2)
    add_bullets(doc, [
        "供水管网、排水管网、隧道桥梁、井盖等其他独立模块的业务平台。本项目仅在综合管廊实体内设置一段燃气管道作为泄漏监测对象，不建设独立燃气管网平台。",
        "面向真实城市部署的防爆认证、消防认证、计量认证、SCADA替代、光纤环网、UWB人员定位、无人机、机器人、区块链和大数据集群。",
        "在教室直接释放甲烷、液化气、丁烷等可燃气体；任何明火、燃烧或高压水喷射演示。",
        "公网高可用、移动App、多租户和大规模设备接入。上述能力只能在核心系统完成后作为扩展。",
    ])
    add_callout(doc, "重要声明", "本样品用于验证综合管廊运维信息流、控制流和可视化方法，不是经认证的生命安全或工业控制设备。所有阈值属于样品演示配置，不能直接用于真实管廊。", fill=AMBER, color="7A5A00")
    add_heading(doc, "2.3 约束与假设", 2)
    add_table(doc, ["类别", "约束/假设", "应对"], [
        ("时间", "从8月25日至9月30日，制作与软件并行", "8月27日前冻结BOM；9月10日先交付闭环MVP"),
        ("人员", "6人岗位不变，部分阶段允许跨岗支援", "采用主责+协作+验收责任，不以职位名称代替交付物"),
        ("加工", "外协3D打印、激光切割和亚克力加工", "提供标准化DXF/STL/STEP和尺寸图；设计可手工修正的装配余量"),
        ("工具", "制作工具不列入采购设备清单", "仅统计进入样品或被消耗的物料"),
        ("网络", "可联网但没有强制云平台", "核心服务部署在展示电脑，使用局域网热点或路由器"),
        ("安全", "积水须可控；气体监测不等于气体释放", "积水限量、物理隔离；甲烷、CO和氧气异常只允许受控信号/数据模拟，烟雾仅使用合规测试气雾"),
    ], [1500, 3900, 3960], font_size=9)

    add_heading(doc, "3 业务流程与使用场景", 1, page_break=True)
    add_heading(doc, "3.1 完整运维闭环", 2)
    pic = doc.add_picture(str(flow), width=Inches(6.35))
    set_alt_text(pic, "完整运维闭环", "从实时监测、异常判定、三维定位、设备联动、告警确认、工单、处置、复核到归档的循环流程")
    add_caption(doc, "图1  综合管廊运维事件闭环")
    add_numbers(doc, [
        "实时监测：STM32周期采集传感器、执行器反馈和通信状态，生成带时间戳和质量标志的遥测。",
        "异常判定：现场侧完成快速保护判定，平台侧完成持续时间、组合条件和分级规则判定。",
        "三维定位：平台依据nodeId/assetId映射查找模型网格，变色、闪烁并自动将相机移动到异常位置。",
        "设备联动：现场控制器优先执行安全联动，例如气体异常启动风机、积水触发声光报警与三维定位、烟雾触发声光报警。",
        "报警确认：值班人员确认收到报警，填写初步判断；确认不等于关闭，异常仍需处置。",
        "工单派发：系统由报警生成工单，记录故障位置、实时值、联动结果、负责人和时限。",
        "现场处置：运维人员执行检查、隔离、排风、人工吸水、复位或更换操作，并记录结果。",
        "恢复复核：传感器值回到恢复阈值且保持规定时间，测试人员/值班人员确认联动设备已复位。",
        "关闭归档：关闭报警和工单，保存完整事件时间线，用于查询、统计和复盘。",
    ])
    add_heading(doc, "3.2 角色与权限", 2)
    add_table(doc, ["系统角色", "允许操作", "禁止/限制"], [
        ("访客/展示", "查看三维、实时值、历史和演示场景", "不能直接控制设备或修改阈值"),
        ("值班员", "确认报警、远程控制、创建工单、填写值班记录", "关键联动解除需二次确认"),
        ("运维员", "接单、处置、上传结果、申请关闭", "不能修改设备编码和系统规则"),
        ("管理员", "设备、阈值、用户、场景、映射、日志和数据维护", "操作全部记录审计日志"),
    ], [1800, 4000, 3560], font_size=9.3)
    add_heading(doc, "3.3 核心场景清单", 2)
    add_table(doc, ["场景", "真实触发方式", "自动联动", "闭环结果"], [
        ("S1 燃气管道泄漏", "燃气管道预设裂缝点LEAK-G01可见；甲烷传感器真实在线，通过隔离信号模拟盒输出越限值", "燃气管道裂缝点定位、风机、声光报警", "燃气泄漏工单→通风/退出模拟→复核→关闭"),
        ("S2 管廊渗水/积水", "从顶板/侧壁预设渗水点的隐藏滴水器向透明接水盘滴入不超过50mL清水，管廊其余区域保持干燥", "B区渗水点定位、声光报警、关闭滴水器/人工吸水", "渗水积水工单→擦干/复位→关闭"),
        ("S3 环境气体异常", "CO或氧气传感器保持真实在线采集；通过隔离的信号模拟盒生成越限值", "气体区红色定位、风机、声光报警", "确认→气体异常工单→通风→信号恢复→关闭"),
        ("S4 温度异常", "低压限温加热片使局部温度缓慢升高", "风机、告警灯、关闭加热源", "温升工单→冷却→温度稳定→关闭"),
        ("S5 烟雾报警", "在小型测试罩内使用合规烟感测试气雾", "声光报警、风机策略按演示配置执行", "火情检查工单→清除气雾→复核→关闭"),
        ("S6 风机故障", "运行命令下断开转速反馈或机械停转", "设备故障报警，禁止持续重启", "检修工单→恢复反馈→试运行→关闭"),
        ("S7 非授权开门", "未登录运维任务时打开检修门", "入口区告警、照明开启、事件抓拍位预留", "安防工单→核查→复位→关闭"),
        ("S8 通信中断", "断开Wi-Fi或ESP8266供电", "现场保护继续，平台设备置灰并报警", "网络工单→重连→补报状态→关闭"),
    ], [1550, 3050, 2280, 2480], font_size=8.3)

    add_heading(doc, "4 需求分析", 1, page_break=True)
    add_heading(doc, "4.1 功能需求", 2)
    functional_rows = [
        ("FR-001", "传感采集", "采集温湿度、分区温度、甲烷、CO、烟雾、氧气、水浸/水位、门磁、风机转速和电流", "必须"),
        ("FR-002", "质量标志", "每个测点包含正常、越限、失联、故障、校准中状态，不能以0代替无数据", "必须"),
        ("FR-003", "本地联动", "网络不可用时仍能执行气体通风、积水声光报警和三维定位状态上报", "必须"),
        ("FR-004", "远程控制", "Web端控制风机、灯、蜂鸣器；命令必须有序号、超时和执行回执", "必须"),
        ("FR-005", "设备台账", "维护区域、设备、测点、执行器、模型网格、接口和状态", "必须"),
        ("FR-006", "三维定位", "告警触发后三维对象变色、闪烁、聚焦并显示实时值与事件", "必须"),
        ("FR-007", "报警管理", "支持预警/报警/紧急三级、确认、抑制说明、恢复、关闭和重复报警合并", "必须"),
        ("FR-008", "工单管理", "报警转工单、负责人、状态、时限、处置记录、复核和关闭", "必须"),
        ("FR-009", "历史趋势", "查询测点、设备状态、报警和工单时间线，支持CSV导出", "必须"),
        ("FR-010", "场景演示", "一键进入演示引导，但真实异常必须来自传感器，不允许只改数据库伪造", "必须"),
        ("FR-011", "配置管理", "阈值、持续时间、恢复差值、联动策略和三维映射可配置", "必须"),
        ("FR-012", "审计日志", "记录登录、控制、阈值修改、报警确认、工单操作和系统重启", "必须"),
        ("FR-013", "联网扩展", "预留反向代理、远程访问和数据备份接口", "后续"),
    ]
    add_table(doc, ["编号", "名称", "要求", "优先级"], functional_rows, [1150, 1700, 5610, 900], font_size=8.2)
    add_heading(doc, "4.2 非功能需求", 2)
    add_table(doc, ["类别", "指标"], [
        ("性能", "局域网内遥测到三维更新的95百分位延迟不超过2秒；控制命令到回执不超过2秒；报警规则从满足条件到平台展示不超过3秒。"),
        ("可靠性", "连续运行4小时无崩溃；30分钟综合场景中遥测缺失率不高于1%；Wi-Fi恢复后15秒内自动重连。"),
        ("安全性", "控制命令鉴权、设备白名单、MQTT账号密码、控制二次确认、最小权限；公网开放时必须增加TLS和反向代理。"),
        ("可维护性", "设备、测点和网格编码统一；配置与代码分离；模块可独立替换；关键接线采用端子和标签。"),
        ("可用性", "展示人员在5分钟培训后能够完成场景；所有告警颜色同时配文字和图标，不能只依靠颜色。"),
        ("可移植性", "两段式实体可通过普通教室门并由两人搬运；Web平台提供Windows启动脚本和Docker可选方案。"),
        ("可追溯性", "每项需求对应设计、负责人、测试用例和验收记录；未通过项目不能标记完成。"),
    ], [1700, 7660], font_size=9)
    add_heading(doc, "4.3 样品阈值基线", 2)
    add_callout(doc, "阈值原则", "下表只用于样品演示和测试。正式实施前应依据具体设备、舱室、传感器说明书和适用标准重新评估。恢复阈值与报警阈值分离，避免边界抖动。", fill=AMBER, color="7A5A00")
    add_table(doc, ["测点", "预警", "报警/紧急", "持续时间", "恢复条件"], [
        ("甲烷", "≥10%LEL", "≥20%LEL；仅信号模拟越限", "10秒", "<5%LEL保持30秒"),
        ("一氧化碳", "≥25 ppm", "≥50 ppm；仅信号模拟越限", "10秒", "<10 ppm保持30秒"),
        ("氧气", "≤20.0%VOL", "≤19.5%VOL；仅信号模拟越限", "10秒", ">20.2%VOL保持30秒"),
        ("局部温度", "≥35℃", "≥40℃；硬件保护50℃", "5秒", "<33℃保持20秒"),
        ("相对湿度", "≥80%RH", "≥90%RH", "30秒", "<75%RH保持60秒"),
        ("水浸", "探头湿润", "高水位开关闭合", "1秒", "探头干燥且高水位复位10秒"),
        ("风机故障", "命令开启但转速低", "命令开启且3秒无有效脉冲", "3秒", "连续有效运行10秒"),
        ("门磁", "检修门打开", "无有效工单/授权时打开", "1秒", "关门并人工确认"),
        ("烟雾", "不单设预警", "探测器干接点动作", "按探测器逻辑", "清除测试气雾并人工复位"),
    ], [1500, 2100, 2900, 1200, 1660], font_size=8.3)

    add_heading(doc, "5 总体技术架构", 1, page_break=True)
    pic = doc.add_picture(str(arch), width=Inches(6.35))
    set_alt_text(pic, "总体技术架构", "现场传感器、STM32控制器、ESP8266和MQTT、平台服务以及Web三维应用的五层架构")
    add_caption(doc, "图2  系统五层架构")
    add_heading(doc, "5.1 技术选型", 2)
    add_table(doc, ["层次", "选型", "理由", "替代/边界"], [
        ("控制器", "STM32F103RCT6 + STM32CubeF1 HAL", "满足指定芯片；接口丰富，适合采集、定时、串口和PWM控制", "不让ESP8266取代主控"),
        ("通信", "ESP8266 ESP-AT，UART连接STM32", "开发快，官方AT支持MQTT发布/订阅，适合短周期", "ESP8266 TLS能力受限；公网阶段再升级"),
        ("协议", "MQTT 3.1.1", "发布订阅适合遥测与命令；Mosquitto成熟轻量", "告警/命令QoS 1，遥测QoS 0，状态使用保留消息"),
        ("后端", "Node.js + Express + MQTT.js + WebSocket", "与Web同语言，接入MQTT和实时推送开发效率高", "避免引入微服务和消息队列集群"),
        ("数据库", "SQLite（WAL模式）", "单机演示足够、部署简单、便于备份", "若后续多用户/云部署再迁移PostgreSQL"),
        ("前端", "Vue 3 + TypeScript + Vite", "组件化、维护活跃、适合仪表盘和流程页面", "不使用已停止维护的Vue 2"),
        ("三维", "Three.js + GLB/glTF + Blender建模", "浏览器直接运行，模型对象可编程映射和交互", "不采用体量较大的游戏引擎"),
        ("部署", "展示电脑本地服务 + 局域网热点/路由器", "互联网不可用时仍能演示", "云部署作为后续增强"),
    ], [1250, 2150, 3650, 2310], font_size=8.25)
    add_heading(doc, "5.2 成熟项目与GitHub复用结论", 2)
    add_table(doc, ["项目", "成熟能力", "本项目决策"], [
        ("ThingsBoard", "设备管理、规则链、告警和仪表板完整", "只借鉴实体模型、规则和报警思想；本期不直接部署，避免Java平台与自研三维整合带来的时间成本"),
        ("Eclipse Mosquitto", "成熟开源MQTT Broker，支持3.1.1/5.0", "直接采用，作为本地消息中枢"),
        ("MQTT.js", "Node.js与浏览器MQTT客户端", "后端直接采用；浏览器默认通过后端WebSocket获取业务数据，避免暴露Broker凭据"),
        ("three.js", "成熟WebGL/WebGPU三维库，支持glTF加载", "直接采用，实现模型加载、拾取、材质状态和相机定位"),
        ("Vue 3", "维护活跃的Web UI框架", "直接采用，构建运维页面和三维容器"),
        ("STM32CubeF1", "官方HAL/LL/CMSIS及示例", "作为固件底座，禁止复制来源不明的驱动代码"),
    ], [1900, 3350, 4110], font_size=8.8)

    add_heading(doc, "6 实体样品设计", 1, page_break=True)
    add_heading(doc, "6.1 总体尺寸与结构", 2)
    pic = doc.add_picture(str(model), width=Inches(6.35))
    set_alt_text(pic, "实体样品布局", "三分区综合管廊样品，包含入口环境区、干燥管廊积水监测区、气体设备区及控制箱")
    add_caption(doc, "图3  实体样品俯视布局建议")
    add_table(doc, ["项目", "设计值", "说明"], [
        ("总尺寸", "约1400 × 650 × 550 mm", "适合教室长桌；两段各约700 mm，便于运输和维护"),
        ("舱体", "单舱剖视、三纵向区域", "范围聚焦综合管廊，不构造其他独立系统"),
        ("框架", "2020铝型材或等效轻型框架", "稳定、可拆、便于走线和安装透明板"),
        ("外壳", "透明亚克力罩 + 可拆检修门", "展示内部管线和联动，不让观众接触滴水盘与电路"),
        ("底座", "两段式封闭底座", "隐藏电源分配和控制箱；B区设置独立高边接水盘"),
        ("供电", "模型内部仅12V/5V/3.3V直流", "220V适配器位于模型外部，入口配置保险和急停"),
        ("重量", "目标不超过25 kg", "两人可搬运；最终以加工图和材料实重核算"),
    ], [1600, 2700, 5060], font_size=9)
    add_heading(doc, "6.2 分区与编码", 2)
    add_table(doc, ["区域", "物理内容", "主要测点/设备", "三维编码"], [
        ("A区", "入口、检修门、环境、照明", "SHT30、DS18B20、门磁、照明", "UT-ZA / DOOR-01 / ENV-01"),
        ("B区", "干燥管廊结构、顶板/侧壁渗水点、隐藏滴水器、接水盘", "水浸、高水位、声光报警", "UT-ZB / SEEP-W01 / LEAK-W01"),
        ("C区", "燃气管道、预设裂缝点、多气体监测、风机、烟感和设备区", "CH₄、CO、O₂、烟感、风机转速、电流、声光报警", "UT-ZC / PIPE-G01 / LEAK-G01 / GAS-01 / FAN-01"),
        ("控制区", "STM32、通信、接口PCB、电源分配", "控制器状态、网络状态、急停", "CTRL-01 / NET-01 / PWR-01"),
    ], [1100, 3000, 3250, 2010], font_size=8.7)
    add_heading(doc, "6.3 实体与三维一致性规则", 2)
    add_bullets(doc, [
        "每个实体区域、设备、测点和执行器粘贴可见编码标签，编码与数据库asset_id、MQTT nodeId、GLB meshName完全一致。",
        "模型坐标以实体左前下角为原点，单位统一为毫米；导出GLB时按比例换算但不改变对象名称。",
        "可拆部件使用插接端子，接口标签包含电压、信号方向和端口号；禁止只依靠线色判断。",
        "滴水演示点、气体传感器安装区和电路物理隔离；所有液体仅允许进入独立接水盘，接口PCB高于可能积水位置。",
    ])
    add_heading(doc, "6.4 外协加工输出", 2)
    add_table(doc, ["文件", "内容", "责任人", "验收点"], [
        ("结构尺寸图PDF", "总装、分段、孔位、板厚和紧固件", "王为", "尺寸闭合、可运输、可装配"),
        ("DXF", "亚克力和底板激光切割轮廓", "王为", "单位mm、无重复线、孔径补偿"),
        ("STL/STEP", "传感器座、管夹、风机罩和测试仓", "王为/胡雨皓", "朝向、壁厚、螺孔和装配间隙"),
        ("GLB", "Web三维模型及命名网格", "王露帆/胡雨皓", "对象编码、面数、材质和加载性能"),
    ], [1800, 3100, 1700, 2760], font_size=8.7)

    add_heading(doc, "7 硬件系统与物料方案", 1, page_break=True)
    add_heading(doc, "7.1 硬件组成", 2)
    bom = [
        ("H-01", "STM32F103RCT6开发板", "1", "原型主控，预留SWD、串口、I²C、SPI、ADC和PWM", "60-120"),
        ("H-02", "ESP8266 ESP-01S及转接板", "2", "1用1备；使用官方ESP-AT，UART连接STM32", "30-60"),
        ("H-03", "SHT30温湿度模块", "1", "A区环境基准测量，I²C", "25-60"),
        ("H-04", "DS18B20防水温度探头", "3", "A/B/C区局部温度，一总线，分配唯一ROM", "30-60"),
        ("H-05", "甲烷可燃气体传感器", "1", "优先选0-100%LEL、UART/RS485输出的工业级模块；真实采集，演示越限由隔离信号模拟", "300-900"),
        ("H-06", "一氧化碳电化学传感器", "1", "优先选带温度补偿、UART/RS485输出模块；真实采集，禁止用CO气体测试", "300-900"),
        ("H-07", "氧气电化学传感器", "1", "优先选0-25%VOL、UART/RS485输出模块；真实采集，禁止置换教室空气", "350-1000"),
        ("H-08", "四线光电烟雾探测器（干接点）", "1", "12V供电，继电器触点经光耦输入", "50-120"),
        ("H-09", "水浸探头/漏水绳接口", "2", "泄漏点和控制箱底部，数字隔离输入", "30-100"),
        ("H-10", "高水位浮球开关", "1", "接水盘高高液位独立保护", "10-30"),
        ("H-11", "门磁开关", "1", "检修门状态，数字输入", "5-15"),
        ("H-11", "三线12V风机", "1", "PWM/开关控制及转速反馈", "35-80"),
        ("H-15", "低压限温加热片+温控熔断", "1", "温度异常演示，硬件上限约50℃", "30-80"),
        ("H-16", "声光报警、LED照明/状态灯", "1批", "报警、分区和正常照明", "60-150"),
        ("H-17", "INA219电流检测模块", "1", "风机运行反馈，I²C读取", "15-35"),
        ("H-18", "MOSFET/继电器驱动与光耦输入", "1批", "感性负载续流、隔离和状态反馈", "80-180"),
        ("H-19", "12V电源、5V/3.3V降压、保险、急停", "1套", "分域供电和保护；外部适配器", "150-300"),
        ("H-20", "接口PCB及焊接物料", "2套", "1主1备，端子、连接器、丝印和测试点", "150-350"),
        ("H-21", "高边接水盘、隐藏滴水器、量杯/注射器和吸水材料", "1套", "仅用于顶板/侧壁预设渗水点不超过50mL的受控渗水演示；不形成循环水路", "60-160"),
        ("H-22", "隔离式多路传感器信号模拟盒", "1套", "用于甲烷、CO、氧气的异常值测试；不接入、不释放真实危险气体", "80-250"),
        ("H-23", "结构材料及外协加工件", "1套", "铝型材、亚克力、3D打印支架和紧固件", "600-1400"),
        ("H-24", "线材、端子、标签、热缩管和备件", "1批", "不包含制作工具", "150-300"),
    ]
    add_table(doc, ["编号", "名称", "数量", "用途/要求", "估算(元)"], bom, [900, 2380, 700, 4300, 1080], font_size=7.8)
    add_body(doc, "采购说明：以上为2026年8月的区间预算，用于方案控制而非供应商报价。专用气体传感器和外协结构价格受规格、运输和商家影响最大，采购前必须取得链接/报价、交期、通信协议和接口照片。制作工具不计入本表。")
    add_heading(doc, "7.2 传感器选择逻辑", 2)
    add_table(doc, ["问题", "设计结论"], [
        ("为什么采用三类专用气体传感器", "甲烷采用%LEL可燃气体传感器，CO与氧气采用电化学模块，均保留真实环境采集；它们的性能与量程以采购模块数据手册为准。"),
        ("为什么不用MQ系列作为定量主传感器", "MQ系列适合存在性/趋势演示，但需要长时间预热、受温湿度和交叉气体影响，不能承担准确浓度或安全联锁。"),
        ("为什么不配置流量监测", "本样品是干燥管廊，不运行循环水工艺。水浸/水位用于顶板/侧壁少量受控渗水演示；高水位浮球用于防溢出保护，因此不采购流量计、循环泵或电磁阀。"),
        ("为什么烟感用干接点", "四线光电烟感自带检测逻辑，干接点易于隔离接入，避免直接处理敏感模拟信号。"),
        ("为什么设备状态含转速和电流", "只读取控制输出无法证明设备真正运行；转速/电流提供执行反馈，可识别断线、卡转和空转。"),
    ], [2500, 6860], font_size=9)
    add_heading(doc, "7.3 接口PCB策略", 2)
    add_bullets(doc, [
        "9月10日前使用STM32F103RCT6现成开发板完成MVP，不等待PCB交付。",
        "定制PCB定位为接口与驱动背板：开发板插接、传感器端子、光耦输入、MOSFET/继电器输出、ESP8266接口、电源保护和测试点。这样既能完成PCB设计与焊接，又不把高风险主控最小系统调试压到关键路径。",
        "PCB通过后保留1套面包板/模块化后备链路；若焊接板出现问题，最终展示仍可回退到已验收的开发板方案。",
        "原理图评审必须检查电压域、感性负载续流、ESP8266峰值电流、地线回流、I²C上拉、接口防反接和丝印。",
    ])
    add_heading(doc, "7.4 电气安全", 2)
    add_table(doc, ["风险", "硬件措施", "软件措施"], [
        ("短路/过流", "12V入口保险、分支自恢复保险、端子防反接", "上电自检，异常电流关闭负载"),
        ("风机反向电动势", "MOSFET驱动和续流二极管，必要时TVS", "命令最小启停间隔和转速异常告警"),
        ("水进入电路", "高边接水盘、控制箱抬高、滴水环、接插件向下", "水浸触发声光报警和滴水演示停止；人工吸水复位"),
        ("加热过温", "独立温控开关或温度保险，功率限流", "50℃硬停止，超时自动断电"),
        ("急停", "物理急停切断执行器12V，主控保持供电记录事件", "急停状态上报，人工复位后方可重新控制"),
    ], [1700, 4050, 3610], font_size=8.8)

    add_heading(doc, "8 嵌入式软件设计", 1, page_break=True)
    add_heading(doc, "8.1 软件分层", 2)
    add_table(doc, ["层", "模块", "职责"], [
        ("BSP/HAL", "GPIO、ADC、TIM、UART、I²C、1-Wire、看门狗", "完成芯片和板级资源封装"),
        ("Driver", "SHT30、CH₄、CO、O₂、DS18B20、烟感、水浸、门磁、INA219、风机", "统一init/read/self_test接口"),
        ("Service", "采集调度、滤波、校准、质量标志、报警、联动、命令、事件", "实现业务状态机"),
        ("Communication", "ESP-AT、MQTT帧、重连、队列、心跳、命令回执", "与平台可靠交互"),
        ("Application", "main、场景模式、参数管理、设备安全状态", "组合运行并对外呈现"),
    ], [1500, 3250, 4610], font_size=9.2)
    add_heading(doc, "8.2 调度周期", 2)
    add_table(doc, ["任务", "周期/触发", "超时与降级"], [
        ("数字量扫描", "10 ms", "连续采样去抖；急停直接硬件生效"),
        ("DS18B20", "1 s", "CRC失败3次置故障"),
        ("SHT30", "2 s", "I²C复位后重试；失败保留最后值并标记stale"),
        ("CH₄ / CO / O₂", "1 s", "按模块协议轮询；连续失败置离线，预热期标识为校准中"),
        ("INA219", "500 ms", "越流立即停负载并上报"),
        ("遥测发布", "1 s", "队列满时保留告警和最新状态，丢弃过期普通遥测"),
        ("心跳", "10 s", "平台30秒未收到则判离线"),
        ("看门狗", "主循环周期内喂狗", "只有全部关键任务健康才喂狗"),
    ], [2000, 2200, 5160], font_size=8.8)
    add_heading(doc, "8.3 现场联动优先级", 2)
    add_table(doc, ["优先级", "条件", "动作"], [
        ("P0", "急停、过流、过温", "立即切断相关执行器，不等待网络"),
        ("P1", "多气体报警", "启动风机、声光报警；禁止远程关闭风机，直到恢复并人工确认"),
        ("P1", "高水位", "停止滴水演示、声光报警并提示人工吸水；不自动启动水泵"),
        ("P1", "烟感", "声光报警；切断加热源；风机策略由场景配置且必须解释"),
        ("P2", "普通预警", "状态灯和平台提示，不强制停机"),
        ("P3", "远程控制", "仅在无更高优先级保护且命令合法时执行"),
    ], [1100, 3000, 5260], font_size=9)
    add_heading(doc, "8.4 命令状态机", 2)
    add_body(doc, "命令流程为 RECEIVED → VALIDATED → EXECUTING → SUCCEEDED/FAILED/TIMEOUT。每条命令包含cmdId、目标设备、目标状态、发起人、时间和过期时间；STM32必须去重，不能因为MQTT QoS 1重复投递而重复动作。执行后发布带cmdId的回执，平台只在收到回执后更新“已执行”状态。")
    add_heading(doc, "8.5 固件质量要求", 2)
    add_bullets(doc, [
        "禁止在中断中进行长时间I²C/UART通信；中断只记录事件或搬运数据。",
        "所有传感器驱动返回值必须检查，数据结构包含value、timestamp/sequence和quality。",
        "阈值采用参数表，不在业务逻辑中散落魔法数字；参数带版本和CRC。",
        "提供sensor_sim编译选项供无硬件联调，但最终验收必须关闭模拟并使用真实传感器。",
        "固件版本、编译时间、Git提交短哈希通过状态主题上报。",
    ])

    add_heading(doc, "9 通信、数据模型与接口", 1, page_break=True)
    add_heading(doc, "9.1 MQTT主题", 2)
    add_table(doc, ["主题", "方向", "QoS/Retain", "用途"], [
        ("ut/v1/ctrl-01/telemetry", "设备→平台", "0/否", "周期遥测，允许丢弃过期帧"),
        ("ut/v1/ctrl-01/state", "设备→平台", "1/是", "设备、执行器、固件和保护状态"),
        ("ut/v1/ctrl-01/alarm", "设备→平台", "1/否", "现场级报警和恢复事件"),
        ("ut/v1/ctrl-01/cmd", "平台→设备", "1/否", "控制与参数命令"),
        ("ut/v1/ctrl-01/cmd_ack", "设备→平台", "1/否", "命令接收与执行回执"),
        ("ut/v1/ctrl-01/status", "设备→平台", "1/是", "online/offline，结合遗嘱消息"),
    ], [4050, 1400, 1500, 2410], font_size=8.7)
    add_heading(doc, "9.2 遥测报文", 2)
    add_code(doc, '''{
  "schema": "ut.telemetry.v1",
  "deviceId": "CTRL-01",
  "seq": 3812,
  "ts": "2026-09-08T10:15:21.420+08:00",
  "values": {
    "ENV-01.temp": {"v": 27.4, "u": "degC", "q": "good"},
    "GAS-01.ch4": {"v": 0.0, "u": "%LEL", "q": "good"},
    "GAS-02.co": {"v": 0.0, "u": "ppm", "q": "good"},
    "GAS-03.o2": {"v": 20.9, "u": "%VOL", "q": "good"},
    "LEAK-G01.ch4": {"v": 0.0, "u": "%LEL", "q": "good"},
    "SEEP-W01.wet": {"v": false, "u": "bool", "q": "good"},
    "FAN-01.rpm": {"v": 1260, "u": "rpm", "q": "good"}
  }
}''')
    add_heading(doc, "9.3 命令报文", 2)
    add_code(doc, '''{
  "schema": "ut.command.v1",
  "cmdId": "CMD-20260908-0012",
  "target": "FAN-01",
  "action": "set",
  "params": {"state": "on"},
  "requestedBy": "operator-01",
  "expiresAt": "2026-09-08T10:16:00+08:00"
}''')
    add_heading(doc, "9.4 编码与时间", 2)
    add_bullets(doc, [
        "设备编码格式：类别-两位序号，例如FAN-01、PUMP-D01；区域编码UT-ZA/UT-ZB/UT-ZC。",
        "所有服务端时间使用ISO 8601并包含时区；STM32无RTC时使用启动毫秒和序列号，平台接收时补充服务器时间。",
        "单位固定：温度degC、湿度%RH、甲烷%LEL、CO ppm、氧气%VOL、转速rpm、电流A；数据库保存数值和单位定义。",
        "对QoS 1消息使用eventId/cmdId去重；平台对seq回退或跳号生成诊断事件。",
    ])

    add_heading(doc, "10 Web三维数字孪生", 1, page_break=True)
    add_heading(doc, "10.1 页面结构", 2)
    add_table(doc, ["页面", "核心内容"], [
        ("综合态势", "全屏三维、设备树、实时指标、未确认报警、联动状态和快捷视角"),
        ("设备详情", "基本信息、实时值、历史曲线、控制、最近事件和模型定位"),
        ("报警中心", "分级、确认、恢复、关闭、关联工单、筛选和事件时间线"),
        ("运维工单", "待派发、处理中、待复核、已关闭；负责人、时限、步骤和记录"),
        ("历史分析", "多测点曲线、事件叠加、报警次数、设备运行时长和CSV导出"),
        ("系统配置", "设备、测点、阈值、联动、用户、模型映射和演示场景"),
    ], [2000, 7360], font_size=9.3)
    add_heading(doc, "10.2 三维模型制作规范", 2)
    add_table(doc, ["项目", "规范"], [
        ("坐标", "与实体统一原点和方向；单元比例一致，导出前应用变换"),
        ("命名", "关键网格使用资产编码，如MESH_FAN_01、MESH_LEAK_W01；装饰网格可合并"),
        ("性能", "首版GLB建议不超过15 MB、三角面不超过20万；纹理使用WebP/压缩，避免4K大图"),
        ("交互", "关键对象具有透明拾取区域；鼠标悬停显示名称，点击打开详情"),
        ("状态", "normal绿色/原材质、warning黄色、alarm红色、offline灰色；同时使用图标和文字"),
        ("定位", "报警调用focusAsset(assetId)，相机平滑移动，目标高亮并显示区域路径"),
    ], [1800, 7560], font_size=9)
    add_heading(doc, "10.3 映射配置", 2)
    add_code(doc, '''{
  "assetId": "LEAK-G01",
  "zoneId": "UT-ZC",
  "meshNames": ["MESH_PIPE_G01", "MESH_LEAK_G01", "MESH_ZONE_C"],
  "telemetryKeys": ["LEAK-G01.ch4", "GAS-02.co", "GAS-03.o2"],
  "cameraPreset": "camera_zone_c",
  "alarmRule": "RULE_GAS_MULTI_01"
}''')
    add_heading(doc, "10.4 三维验收", 2)
    add_bullets(doc, [
        "模型与实体设备数量、位置、标签和方向一致。",
        "任一核心告警在3秒内定位到正确区域和设备，不能只在列表中显示。",
        "离线设备置灰且保留最后值与最后通信时间，不能显示为0。",
        "低性能展示电脑上保持可操作，目标帧率不低于30 FPS；必要时降低阴影、后处理和模型面数。",
    ])

    add_heading(doc, "11 平台服务与数据库", 1, page_break=True)
    add_heading(doc, "11.1 后端模块", 2)
    add_table(doc, ["模块", "职责"], [
        ("mqtt-adapter", "连接Broker、订阅、校验schema、去重、发布命令和处理回执"),
        ("device-service", "设备台账、在线状态、最后值、资产与测点关系"),
        ("alarm-engine", "阈值、持续时间、组合规则、分级、恢复和抑制"),
        ("control-service", "权限、互锁、命令序列、超时、回执和审计"),
        ("workorder-service", "报警转工单、流转、处置、复核和关闭"),
        ("realtime-gateway", "通过WebSocket向前端推送遥测、报警、设备和工单变更"),
        ("report-service", "趋势、事件时间线、统计和CSV导出"),
        ("auth-audit", "用户角色、会话和所有关键操作审计"),
    ], [2400, 6960], font_size=9.2)
    add_heading(doc, "11.2 数据表", 2)
    add_table(doc, ["表", "关键字段", "说明"], [
        ("zones", "id, name, model_path", "管廊区域"),
        ("assets", "id, zone_id, type, mesh_name, status", "传感器、执行器和结构资产"),
        ("points", "id, asset_id, key, unit, thresholds", "测点定义"),
        ("telemetry", "point_id, ts, value, quality, seq", "时序遥测；按point_id+ts索引"),
        ("alarms", "id, rule_id, level, state, first_ts, recover_ts", "报警生命周期"),
        ("alarm_events", "alarm_id, action, user_id, ts, note", "报警操作时间线"),
        ("work_orders", "id, alarm_id, assignee, state, due_at", "运维工单"),
        ("work_order_logs", "order_id, action, result, ts, attachments", "处置与复核记录"),
        ("commands", "cmd_id, target, payload, state, request_ts, ack_ts", "控制命令审计"),
        ("users/audit_logs", "role, action, target, before, after, ts", "权限与审计"),
    ], [1900, 4050, 3410], font_size=8.7)
    add_heading(doc, "11.3 数据保留和备份", 2)
    add_bullets(doc, [
        "开发阶段遥测保留全部；稳定后可按1秒原始数据保留30天，较长期数据按分钟聚合。",
        "每天首次启动和最终验收前复制SQLite数据库、配置和模型文件；备份文件带日期时间。",
        "系统启动时执行数据库迁移并记录版本；禁止直接手改生产数据库。",
        "演示前提供clean-demo-data脚本，只清理演示数据，不删除设备、规则和用户配置。",
    ])

    add_heading(doc, "12 报警、联动与工单设计", 1, page_break=True)
    add_heading(doc, "12.1 报警状态机", 2)
    add_body(doc, "状态依次为 NORMAL → PENDING → ACTIVE_UNACK → ACTIVE_ACK → RECOVERED → CLOSED。达到阈值先进入PENDING并等待持续时间；恢复也需要保持时间。ACK只表示人员已收到，不能清除现场联动；CLOSED必须在恢复、填写处置记录并通过复核后执行。")
    add_heading(doc, "12.2 组合规则", 2)
    add_table(doc, ["规则", "输入条件", "结论/动作"], [
        ("R-CH4", "甲烷持续越限且数据质量good", "可燃气体报警；风机和声光联动"),
        ("R-CO", "CO持续越限且数据质量good", "有毒气体报警；风机和声光联动"),
        ("R-O2", "氧气持续低于阈值且数据质量good", "缺氧报警；风机和声光联动"),
        ("R-GLEAK", "LEAK-G01甲烷持续越限且数据质量good", "燃气管道泄漏；定位PIPE-G01/LEAK-G01，风机、声光报警并创建工单"),
        ("R-WSEEP", "SEEP-W01水浸=真并持续", "管廊渗水/积水；定位SEEP-W01，声光报警、停止滴水演示并创建工单"),
        ("R-WCRIT", "高水位=真", "紧急积水；保持滴水演示停止，提示人工吸水后复核"),
        ("R-FAN", "风机命令on且转速无脉冲或电流异常", "设备故障；限制自动重启次数"),
        ("R-TEMP", "分区温度越限", "温度报警；切加热、启动风机"),
        ("R-DOOR", "门开且无有效运维任务/授权", "安防报警；入口照明开启"),
        ("R-OFFLINE", "30秒无心跳", "通信报警；三维置灰；现场联动保持"),
    ], [1650, 4200, 3510], font_size=8.8)
    add_heading(doc, "12.3 工单字段与流转", 2)
    add_table(doc, ["阶段", "必填内容", "进入条件", "退出条件"], [
        ("待派发", "来源报警、位置、级别、建议步骤", "报警确认或自动创建", "指定负责人和截止时间"),
        ("处理中", "到场时间、检查项、照片/备注、采取措施", "负责人接单", "提交处置结果"),
        ("待复核", "恢复测点、试运行结果、遗留风险", "处置完成", "复核人确认通过或退回"),
        ("已关闭", "根因、最终结论、关闭时间", "报警已恢复且复核通过", "归档，不允许直接修改"),
    ], [1700, 3300, 2200, 2160], font_size=8.7)
    add_heading(doc, "12.4 控制互锁", 2)
    add_bullets(doc, [
        "高水位时禁止开始滴水演示；仅允许人工确认接水盘已清空后复位。",
        "任一气体报警未恢复时禁止关闭通风风机，除非物理急停或管理员执行带原因的安全解除。",
        "烟感动作或温度硬限时禁止开启加热片。",
        "急停状态下拒绝所有开启类命令，只允许查询状态。",
        "同一执行器在最小启停间隔内拒绝重复切换，保护风机、照明和电源。",
    ])

    add_heading(doc, "13 气体、积水演示与展示安全方案", 1, page_break=True)
    add_heading(doc, "13.1 多气体监测与异常模拟", 2)
    add_callout(doc, "安全边界", "甲烷、CO和氧气传感器应安装并真实采集环境值，但教室展示不得释放甲烷、液化气、丁烷、CO或氧气，也不得用打火机放气或点火。异常状态仅由隔离式信号模拟盒产生；烟雾场景仅在小型测试罩内使用合规烟感测试气雾。", fill=AMBER, color="7A5A00")
    add_numbers(doc, [
        "传感器完成上电自检、环境基线记录和通信质量检查；未通过自检的通道必须标识为故障，不能伪装为正常值。",
        "信号模拟盒须与传感器供电和通信端隔离，并可分别输出甲烷、CO、氧气的正常、预警、报警和恢复值。",
        "先展示真实环境基线，再切换单一异常通道；平台应显示测点、数值、报警、风机与声光联动、工单及恢复过程。",
        "烟雾仅在小型测试罩内使用合规烟感测试气雾；禁止燃烧纸张、使用打火机火焰或任何可燃气体。",
        "每次演示前后记录真实基线、模拟峰值、报警响应和恢复时间；异常时立即停止演示并复位。",
    ])
    add_heading(doc, "13.2 真实管廊渗水/积水演示", 2)
    add_bullets(doc, [
        "样品按干燥管廊设计，不设置循环水路、流量计、循环泵或电磁阀，也不连接建筑自来水。",
        "水场景仅通过顶板/侧壁预设渗水点的隐藏滴水器向高边透明接水盘加入不超过50mL清水；接水盘配置水浸和高水位双检测。",
        "滴水器、预设渗水点和接水盘全部位于B区独立防水范围；控制PCB和插座高于最高可能水位。",
        "展示结束由人员吸水、擦干并确认水位复位；运输时接水盘必须保持干燥。",
    ])
    add_heading(doc, "13.3 展示前安全检查", 2)
    add_table(doc, ["检查项", "通过条件", "负责人"], [
        ("供电", "适配器、保险、急停、线缆和端子无损伤；内部无220V", "王为/胡雨皓"),
        ("渗水/积水演示", "接水盘干燥、高水位有效、滴水量不超过50mL且电路隔离", "王为/史润佳"),
        ("气体监测", "CH₄、CO、O₂通道真实基线、通信和模拟盒隔离均正常；无气瓶、无打火机", "车晨星/胡雨皓"),
        ("温升", "硬件温控和软件50℃断电测试通过", "闵昊/胡雨皓"),
        ("控制", "急停、互锁、命令回执和失联保护通过", "闵昊/王露帆"),
        ("场地", "模型稳定、观众不可触及活动/带水部件、演示人员明确", "车晨星/史润佳"),
    ], [2400, 4760, 2200], font_size=8.8)

    add_heading(doc, "14 团队组织与完整分工", 1, page_break=True)
    add_heading(doc, "14.1 固定岗位", 2)
    add_table(doc, ["姓名", "固定岗位", "主责工作包", "辅助工作"], [
        ("车晨星", "项目组长", "需求基线、架构决策、进度、采购、接口协调、版本和最终验收", "文档统稿、集成问题协调、展示组织"),
        ("王露帆", "软件工程师", "后端、数据库、Web前端、Three.js集成、API和部署脚本", "模型映射、通信联调、演示页面"),
        ("史润佳", "运维工程师", "运维流程、报警/工单规则、设备台账、部署运行、演示SOP", "前期硬件装配、线缆标签、现场联调"),
        ("王为", "硬件开发工程师", "实体结构、电气原理图、传感器接口、驱动电路、PCB、BOM和装配", "加工对接、硬件故障定位"),
        ("胡雨皓", "测试工程师", "测试计划、用例、标定、缺陷、回归、验收证据和安全检查", "前期台架接线、3D设备清单和模型核对"),
        ("闵昊", "嵌入式工程师", "STM32固件、驱动、调度、联动、ESP-AT/MQTT、命令和看门狗", "PCB接口评审、传感器选型验证"),
    ], [1300, 1900, 3800, 2360], font_size=8.5)
    add_heading(doc, "14.2 工作包责任矩阵", 2)
    add_table(doc, ["工作包", "主责(A/R)", "协作(C)", "验收(V)", "交付物"], [
        ("WP01 需求与范围", "车晨星", "全员", "胡雨皓", "需求基线、追踪矩阵"),
        ("WP02 实体结构", "王为", "史润佳、胡雨皓", "车晨星", "尺寸图、DXF/STL、装配图"),
        ("WP03 硬件与PCB", "王为", "闵昊、史润佳", "胡雨皓", "原理图、PCB、BOM、接线图"),
        ("WP04 嵌入式", "闵昊", "王为", "胡雨皓", "固件、驱动、协议、联动"),
        ("WP05 通信与后端", "王露帆", "闵昊", "胡雨皓", "Broker配置、API、数据库"),
        ("WP06 Web三维", "王露帆", "胡雨皓、史润佳", "车晨星", "GLB、映射、前端页面"),
        ("WP07 运维业务", "史润佳", "王露帆、车晨星", "胡雨皓", "报警、工单、SOP、台账"),
        ("WP08 测试验收", "胡雨皓", "全员", "车晨星", "用例、缺陷、报告、证据"),
        ("WP09 集成展示", "车晨星", "全员", "全员会签", "演示脚本、视频、最终包"),
    ], [1800, 1550, 2200, 1450, 2360], font_size=8.3)
    add_heading(doc, "14.3 分阶段人员投入", 2)
    add_table(doc, ["阶段", "车晨星", "王露帆", "史润佳", "王为", "胡雨皓", "闵昊"], [
        ("8/25-8/27", "范围/计划", "架构骨架", "流程/台账", "结构/BOM", "测试基线/选型验证", "接口/驱动验证"),
        ("8/28-9/4", "采购/协调", "后端+三维骨架", "装配支援/规则", "台架+加工图", "台架测试/模型清单", "采集+控制+通信"),
        ("9/5-9/10", "MVP集成", "实时三维/报警", "工单/演示流程", "水气设备装配", "端到端测试", "联动/稳定性"),
        ("9/11-9/18", "变更控制", "完整页面/历史", "部署/运维文档", "PCB/最终结构", "回归/安全", "PCB适配/异常处理"),
        ("9/19-9/25", "验收组织", "缺陷修复", "全流程演练", "硬件整改", "系统/场景验收", "固件整改"),
        ("9/26-9/30", "统稿/交付", "部署包/视频", "SOP/交付清单", "图纸/BOM归档", "最终报告/证据", "固件发布/说明"),
    ], [1500, 1310, 1310, 1310, 1310, 1310, 1310], font_size=7.5)
    add_heading(doc, "14.4 协作规则", 2)
    add_bullets(doc, [
        "每日15分钟站会：昨天完成、今天计划、阻塞项；阻塞超过半天立即在项目看板升级。",
        "接口先写文档再联调。硬件引脚、MQTT主题、JSON字段、模型编码的任何改动必须经主责双方确认。",
        "任务完成定义：代码/图纸提交、基本自测通过、文档更新、验收人签字；只有口头报告不算完成。",
        "测试工程师可以拒绝无证据的完成状态；项目组长负责范围和截止时间，不代替专业验收。",
        "前期史润佳、胡雨皓优先支援硬件台架、标签和设备清单；进入系统测试后恢复各自主责。",
    ])

    add_heading(doc, "15 实施进度与里程碑", 1, page_break=True)
    add_heading(doc, "15.1 总体计划", 2)
    schedule = [
        ("8/25-8/27", "M0 需求与架构冻结", "需求基线、场景、尺寸、BOM、接口v0.1、采购下单", "车晨星/全员"),
        ("8/28-8/31", "M1 台架打通", "STM32读取首批传感器；控制风机/灯/声光报警；Web骨架和三维白模", "王为/闵昊/王露帆"),
        ("9/1-9/4", "M2 数据链路", "ESP8266 MQTT、后端入库、WebSocket、三维映射；加工文件下单", "王露帆/闵昊/王为"),
        ("9/5-9/7", "M3 场景集成", "燃气管道泄漏、管廊渗水/积水、温度、烟感、设备故障至少4个场景贯通", "全员"),
        ("9/8-9/10", "MVP验收", "实时采集、三维定位、告警、联动、确认、工单和恢复闭环", "车晨星/胡雨皓"),
        ("9/11-9/14", "M4 PCB与完整业务", "接口PCB发板/焊接；报警规则、历史、权限和审计完善", "王为/王露帆/史润佳"),
        ("9/15-9/18", "M5 最终实体", "外协件装配、PCB接入、线缆标签和两段式结构完成", "王为/史润佳/闵昊"),
        ("9/19-9/22", "M6 全场景", "7个场景、互锁、断网恢复和四小时稳定性通过", "胡雨皓/全员"),
        ("9/23-9/25", "M7 验收候选", "缺陷清零到可接受级别，文档和部署包候选版", "车晨星/胡雨皓"),
        ("9/26-9/28", "M8 交付制作", "演示视频、汇报材料、最终报告和源代码归档", "全员"),
        ("9/29-9/30", "最终验收", "完整演示、清单会签、备份、版本标签和交付", "车晨星/全员"),
    ]
    add_table(doc, ["日期", "里程碑", "完成标准", "主责"], schedule, [1500, 2200, 4360, 1300], font_size=8.2)
    add_heading(doc, "15.2 9月10日MVP最小范围", 2)
    add_bullets(doc, [
        "实体台架已能真实读取甲烷、CO、氧气、温度、水浸/水位和至少一个设备反馈。",
        "已能真实控制风机、照明和声光报警中的核心设备。",
        "STM32→ESP8266→Mosquitto→后端→数据库→Web→三维完整链路运行。",
        "燃气管道泄漏和管廊渗水/积水两个强制场景完成三维定位、报警、联动、确认、工单、恢复和关闭。",
        "即使最终外壳或PCB尚未完成，MVP必须在可靠台架上可重复演示三次。",
    ])
    add_heading(doc, "15.3 变更控制", 2)
    add_body(doc, "8月27日后新增范围必须填写变更记录，包含原因、收益、工作量、对9月10日和9月30日的影响、替代项和批准人。任何影响强制场景、三维定位、真实联动或安全的变更不得口头执行。非核心美化、云功能和高级统计必须排在最终验收之后。")

    add_heading(doc, "16 测试与验收计划", 1, page_break=True)
    add_heading(doc, "16.1 测试层级", 2)
    add_table(doc, ["层级", "对象", "进入条件", "退出条件"], [
        ("单元/台架", "传感器、驱动、执行器和后端模块", "接口和样件可用", "正常、边界、断线和错误用例通过"),
        ("接口", "UART、MQTT、JSON、WebSocket和数据库", "双方接口版本一致", "字段、超时、重复、重连和错误码通过"),
        ("集成", "实体到三维与控制回路", "单元测试通过", "端到端时延、回执、定位和联动通过"),
        ("场景", "7个异常和完整运维闭环", "安全检查通过", "每个场景连续演示3次成功"),
        ("系统", "稳定性、性能、安全、恢复和部署", "关键缺陷关闭", "指标达标，无阻断缺陷"),
        ("验收", "全部交付物", "候选版本冻结", "清单、证据、演示和文档会签"),
    ], [1500, 2900, 2350, 2610], font_size=8.6)
    add_heading(doc, "16.2 关键测试用例", 2)
    cases = [
        ("TC-01", "多气体基线", "CH₄、CO、O₂环境值合理、通信稳定、质量good", "H-05至H-07/FR-001"),
        ("TC-02", "甲烷异常模拟", "隔离模拟盒输出越限值后C区定位、风机和声光动作", "S1/FR-003/006"),
        ("TC-03", "CO/氧气恢复", "退出模拟后按恢复条件转RECOVERED，不立即跳变", "FR-007"),
        ("TC-04", "真实管廊渗水/积水", "从顶板/侧壁预设渗水点向接水盘加入少量清水，水浸触发三维定位和声光报警", "S2/FR-003"),
        ("TC-05", "高水位保护", "高水位时停止滴水演示，提示人工吸水并复核", "安全互锁"),
        ("TC-06", "温度异常", "温度达到阈值，切断加热并通风；50℃硬保护有效", "S4"),
        ("TC-07", "烟感", "测试气雾触发干接点，报警和工单链路正确", "S5"),
        ("TC-08", "风机反馈故障", "命令开启但无转速，识别故障而非显示运行", "S6"),
        ("TC-09", "非授权开门", "无有效工单时开门报警；有任务时记录但不报警", "S7"),
        ("TC-10", "通信中断", "平台30秒内判离线，三维置灰，现场保护继续", "S8"),
        ("TC-11", "自动重连", "恢复Wi-Fi后15秒内上线并发布正确状态", "NFR可靠性"),
        ("TC-12", "命令去重", "重复cmdId只执行一次并返回同一结果", "MQTT QoS1"),
        ("TC-13", "命令超时", "设备未回执时平台显示TIMEOUT，不伪装成功", "FR-004"),
        ("TC-14", "三维映射", "每个核心资产逐一触发，定位均与实体标签一致", "O-01"),
        ("TC-15", "工单闭环", "报警→确认→派单→处置→复核→关闭字段完整", "O-04"),
        ("TC-16", "权限", "访客不能控制，值班员受互锁，管理员操作有审计", "FR-012"),
        ("TC-17", "页面刷新", "刷新后报警、工单和执行器状态不丢失", "NFR可靠性"),
        ("TC-18", "连续运行", "4小时无崩溃，遥测缺失率≤1%，无持续内存增长", "O-05"),
        ("TC-19", "急停", "急停立即切执行器，平台记录；复位前拒绝开启", "安全"),
        ("TC-20", "重新部署", "按手册在干净电脑启动并完成基础场景", "可复现性"),
    ]
    add_table(doc, ["编号", "测试", "预期结果", "追踪"], cases, [1000, 1800, 4900, 1660], font_size=8.1)
    add_heading(doc, "16.3 缺陷等级", 2)
    add_table(doc, ["等级", "定义", "最终验收要求"], [
        ("P0 阻断", "安全风险、无法启动、核心场景完全不可用", "必须为0"),
        ("P1 严重", "数据/控制错误、三维定位错误、闭环无法完成", "必须为0"),
        ("P2 一般", "有绕行方案但影响体验或文档", "原则上关闭；遗留须有明确说明"),
        ("P3 轻微", "文字、样式和低影响问题", "记录后可纳入后续"),
    ], [1400, 5000, 2960], font_size=9.1)
    add_heading(doc, "16.4 验收证据", 2)
    add_bullets(doc, [
        "测试记录包含版本、日期、环境、步骤、实际值、截图/视频、结果和测试人。",
        "每个强制场景保留实体全景、三维定位、报警详情、联动反馈、工单和恢复关闭六类证据。",
        "传感器标定/对比记录、气体安全检查、接水盘隔离/滴水量检查和急停测试单独归档。",
        "最终版本使用Git标签，文档、固件、前后端、模型、数据库schema和部署包使用同一版本号。",
    ])

    add_heading(doc, "17 预算与采购计划", 1, page_break=True)
    add_heading(doc, "17.1 预算基线", 2)
    add_table(doc, ["类别", "估算区间(元)", "控制策略"], [
        ("控制、传感与执行器", "1100-2200", "关键模块1用1备；先台架验证再批量购买"),
        ("积水演示与气体监测模块", "1080-3370", "优先采购三类专用气体传感器与隔离信号模拟盒；积水演示仅采用接水盘和滴水器"),
        ("结构与外协加工", "600-1400", "先纸板/简模校核，再下单亚克力和3D打印"),
        ("PCB、线材、端子和备件", "300-650", "PCB两套；高故障率连接件留备件"),
        ("预留与价格波动", "400-700", "约15%-20%预备金"),
        ("项目预计总额", "约3620-8560", "不包含制作工具和已有电脑；以实际报价为准"),
    ], [2600, 1900, 4860], font_size=9)
    add_heading(doc, "17.2 采购优先级", 2)
    add_table(doc, ["优先级", "8月27日前下单", "原因"], [
        ("P0", "甲烷、CO、氧气传感器、STM32板、ESP8266、烟感、水浸和高水位", "决定核心场景且交期/接口风险高"),
        ("P1", "电源、驱动、端子、线材、高边接水盘、滴水器和吸水材料", "影响台架集成与安全"),
        ("P1", "结构加工打样", "外协交期可能影响最终实体"),
        ("P2", "状态灯、装饰件、标签和美化", "不阻塞MVP，可后补"),
    ], [1300, 4900, 3160], font_size=8.9)
    add_heading(doc, "17.3 到货验收", 2)
    add_bullets(doc, [
        "核对型号、接口、电压、数量、外观、资料和退换期限；拍照并登记设备台账。",
        "传感器到货24小时内完成通电、通信和合理性测试；风机完成空载/带载测试。",
        "外协件按尺寸、孔位、平整度、透明度和装配间隙验收，不合格立即反馈商家。",
        "未经过到货测试的器件不得焊接到最终PCB。",
    ])

    add_heading(doc, "18 风险管理", 1, page_break=True)
    risks = [
        ("R1", "专用气体传感器到货晚或接口不兼容", "高", "高", "8/27前下单；先用隔离信号模拟盒完成链路联调；最终验收前完成真实环境基线和通信验证", "车晨星"),
        ("R2", "外协结构延期或尺寸错误", "中", "高", "先简模验证；两段式设计；提供可手工修正孔位和备用支架", "王为"),
        ("R3", "ESP8266通信不稳定", "中", "高", "固定供电、自动重连、USB串口后备、本地Broker", "闵昊"),
        ("R4", "PCB首版错误", "中", "高", "原理图双人评审、2套板、保留开发板台架回退", "王为"),
        ("R5", "气体传感器预热、漂移或交叉敏感", "中", "中", "按数据手册预热；记录基线；隔离信号模拟用于异常链路验收；不以演示阈值作安全结论", "胡雨皓"),
        ("R6", "积水损坏电路", "低", "极高", "高边接水盘、控制箱抬高、急停、高水位保护、滴水量限制和展示前检查", "王为"),
        ("R7", "三维模型过大卡顿", "中", "中", "对象合并、纹理压缩、LOD/关闭阴影、15MB目标", "王露帆"),
        ("R8", "软硬件接口频繁变化", "高", "高", "8/27冻结v0.1；字段/引脚变更必须评审并同步文档", "车晨星"),
        ("R9", "单人软件任务过重", "高", "高", "胡雨皓支援模型映射，史润佳负责业务规则和数据录入，车晨星支援文档", "车晨星"),
        ("R10", "安全要求与场地规定冲突", "中", "极高", "演示前向场地负责人说明仅使用信号模拟、测试气雾和少量滴水；不允许烟雾气雾则改为烟感干接点模拟", "车晨星"),
        ("R11", "临近截止新增功能", "高", "中", "变更控制；云、AI、UWB和移动端列入后续，不进入核心路径", "车晨星"),
        ("R12", "成员缺席/任务阻塞", "中", "高", "主责文档化、关键任务双人知情、每日提交、备份和交叉评审", "全员"),
    ]
    add_table(doc, ["编号", "风险", "概率", "影响", "应对", "责任人"], risks, [700, 1900, 700, 700, 4380, 980], font_size=7.7)
    add_heading(doc, "18.1 风险升级规则", 2)
    add_bullets(doc, [
        "影响9月10日MVP的阻塞超过4小时，主责立即报告项目组长并提出回退方案。",
        "涉及水、电、气体和加热安全的问题立即停止相关测试，不以进度为由继续。",
        "关键器件交期无法保证时，在24小时内完成替代器件接口评估并更新BOM。",
        "风险关闭必须有验证证据；仅说明“已注意”不能关闭。",
    ])

    add_heading(doc, "19 交付、版本与仓库管理", 1, page_break=True)
    add_heading(doc, "19.1 最终交付清单", 2)
    deliverables = [
        ("D01", "实体样品", "干燥管廊、传感器、执行器、接水盘与滴水演示点、多气体监测安装位、控制箱、标签", "王为"),
        ("D02", "嵌入式源代码", "STM32工程、驱动、配置、编译说明、固件bin/hex", "闵昊"),
        ("D03", "通信与平台源代码", "Broker配置、后端、数据库迁移、Web前端和启动脚本", "王露帆"),
        ("D04", "三维资产", "Blender源文件、GLB、纹理、命名表和映射配置", "王露帆/胡雨皓"),
        ("D05", "硬件设计", "原理图、PCB、Gerber、BOM、接线图、端子表和装配图", "王为"),
        ("D06", "项目计划书", "范围、架构、分工、进度、预算、风险和验收", "车晨星"),
        ("D07", "需求规格书", "用例、功能/非功能需求、业务规则和追踪矩阵", "车晨星/史润佳"),
        ("D08", "系统设计书", "硬件、固件、平台、数据库、三维和安全设计", "各模块主责"),
        ("D09", "接口文档", "I/O、引脚、MQTT、JSON、REST/WebSocket、错误码", "闵昊/王露帆"),
        ("D10", "测试报告", "用例、结果、缺陷、性能、稳定性、安全和验收证据", "胡雨皓"),
        ("D11", "部署与使用手册", "安装、启动、配置、备份、恢复、演示和故障处理", "史润佳"),
        ("D12", "演示材料", "演示脚本、演示视频、汇报材料、现场安全检查表", "全员"),
        ("D13", "发布归档", "版本说明、许可证清单、第三方来源、数据库样例和最终标签", "车晨星"),
    ]
    add_table(doc, ["编号", "交付物", "最低内容", "主责"], deliverables, [900, 2000, 5000, 1460], font_size=8.2)
    add_heading(doc, "19.2 仓库建议结构", 2)
    add_code(doc, '''utility-tunnel-digital-twin/
  firmware/       STM32CubeIDE工程、驱动、协议和固件发布
  hardware/       原理图、PCB、Gerber、接线图、结构加工文件
  model/          Blender、GLB、纹理和资产映射
  apps/web/       Vue 3 + Three.js前端
  services/api/   Node.js后端、MQTT接入、数据库迁移
  deploy/         Mosquitto、配置、启动/停止和备份脚本
  docs/           计划、需求、设计、接口、测试、部署、演示
  test/           测试数据、自动化脚本和验收证据索引
  README.md       项目概述、快速启动、目录和版本''')
    add_heading(doc, "19.3 Git工作流", 2)
    add_bullets(doc, [
        "main只保存可演示版本；develop用于集成；feature/firmware、feature/hardware、feature/web3d、feature/ops等分支承载工作。",
        "提交信息使用feat/fix/docs/test/chore前缀并说明模块；禁止一次提交混合大量无关改动。",
        "合并到develop至少由一名非作者检查；涉及接口必须由接口另一方确认。",
        "里程碑标签建议：v0.1-bench、v0.5-mvp、v0.8-rc、v1.0-final。",
        "仓库保持私有协作；不得提交Wi-Fi密码、MQTT密码、个人信息、气体供应商账户或大型临时文件。",
    ])
    add_heading(doc, "19.4 完成定义", 2)
    add_callout(doc, "Definition of Done", "交付物已进入仓库；版本可构建/可打开；自测通过；接口与说明同步；验收人检查；不存在未说明的P0/P1缺陷；安全检查和演示回退方案齐备。")

    add_heading(doc, "附录A 建议I/O分配（冻结前复核开发板原理图）", 1, page_break=True)
    add_table(doc, ["资源", "建议用途", "备注"], [
        ("USART1", "调试串口/日志", "连接USB转串口；生产日志可降级"),
        ("USART2", "ESP8266 ESP-AT", "DMA接收+空闲中断，独立复位脚"),
        ("I²C1", "SHT30、INA219", "核对地址；总线短线并配置上拉"),
        ("TIM3 CH1", "风机PWM", "频率按风机规格确认"),
        ("TIM3 CH2", "风机转速输入", "定时测频"),
        ("GPIO输入", "烟感、水浸、高水位、门磁、急停反馈", "光耦/上拉/去抖，急停另有硬件链路"),
        ("GPIO输出", "风机使能、灯、蜂鸣器", "经MOSFET/继电器，不直接驱动负载"),
        ("1-Wire GPIO", "3个DS18B20", "唯一ROM绑定区域，强上拉视线长评估"),
        ("ADC", "预留压力/模拟量接口", "本期不作为强制测点"),
        ("SWD", "下载和调试", "PCB必须保留标准接口和地"),
        ("IWDG", "独立看门狗", "仅健康任务完成后喂狗"),
    ], [2200, 3500, 3660], font_size=8.9)

    add_heading(doc, "附录B 需求追踪样例", 1, page_break=True)
    add_table(doc, ["需求", "设计", "负责人", "测试", "交付"], [
        ("FR-001真实采集", "H-03至H-11、固件Driver", "王为/闵昊", "TC-01至TC-09", "D01/D02/D05"),
        ("FR-003本地联动", "现场联动优先级与互锁", "闵昊", "TC-02至TC-06、TC-19", "D02/D09"),
        ("FR-006三维定位", "assetId-meshName映射", "王露帆", "TC-14", "D03/D04"),
        ("FR-007报警", "报警状态机和组合规则", "史润佳/王露帆", "TC-02/03/15", "D03/D07"),
        ("FR-008工单", "工单四阶段流转", "史润佳/王露帆", "TC-15", "D03/D11"),
        ("O-05稳定运行", "重连、看门狗、WAL、状态持久化", "闵昊/王露帆", "TC-11/17/18", "D02/D03/D10"),
    ], [1800, 2900, 1700, 1600, 1360], font_size=8.7)

    add_heading(doc, "附录C 演示脚本（8-10分钟）", 1, page_break=True)
    add_table(doc, ["时间", "操作", "界面/实体表现", "讲解重点"], [
        ("0:00-1:00", "启动并展示正常巡检", "三维全景绿色，实时值和设备在线", "实体与三维编码一致"),
        ("1:00-3:00", "执行多气体异常模拟", "C区聚焦，甲烷/CO/氧气异常、风机和声光联动", "真实传感器在线，隔离信号模拟异常，禁止释放危险气体"),
        ("3:00-4:30", "确认报警并生成工单", "事件时间线和工单出现", "确认不等于关闭"),
        ("4:30-6:00", "执行真实管廊渗水/积水", "水浸、高水位、三维定位和声光报警", "顶板/侧壁少量滴水、传感器触发和设备反馈"),
        ("6:00-7:30", "处置与恢复", "退出模拟/停止滴水，通风并人工吸水，数值恢复", "恢复保持时间和复核"),
        ("7:30-9:00", "关闭工单并查看历史", "报警关闭、曲线和完整记录", "闭环和可追溯性"),
        ("9:00-10:00", "展示断网或风机故障", "设备置灰或故障，现场保护仍运行", "故障降级和系统可靠性"),
    ], [1300, 2500, 3300, 2260], font_size=8.6)

    add_heading(doc, "附录D 参考标准、官方资料与开源项目", 1, page_break=True)
    add_body(doc, "资料使用原则：标准用于理解运维服务和工程边界，器件参数以制造商数据手册为准，开源项目用于选型与复用。样品不宣称达到真实工程认证。访问日期均为2026年8月25日。")
    refs = [
        ("[1]", "GB/T 38550-2020《城市综合管廊运营服务规范》（国家标准全文公开系统）", "https://openstd.samr.gov.cn/bzgk/std/newGbInfo?hcno=AA5494CE3C03C754178DD38EB5FA7ED9"),
        ("[2]", "STMicroelectronics, STM32F103RC product page and datasheet", "https://www.st.com/en/microcontrollers-microprocessors/stm32f103rc.html"),
        ("[3]", "STMicroelectronics, STM32CubeF1 official repository", "https://github.com/STMicroelectronics/STM32CubeF1"),
        ("[4]", "Espressif, ESP8266 ESP-AT MQTT Commands", "https://docs.espressif.com/projects/esp-at/en/release-v2.2.0.0_esp8266/AT_Command_Set/MQTT_AT_Commands.html"),
        ("[5]", "OASIS, MQTT Version 3.1.1", "https://docs.oasis-open.org/mqtt/mqtt/v3.1.1/os/mqtt-v3.1.1-os.pdf"),
        ("[6]", "OSHA, Underground Construction: Gases, oxygen and testing requirements", "https://www.osha.gov/laws-regs/regulations/standardnumber/1926/1926.800"),
        ("[7]", "Sensirion, SHT3x-DIS datasheet", "https://sensirion.com/media/documents/213E6A3B/63A5A569/Datasheet_SHT3x_DIS.pdf"),
        ("[8]", "Eclipse Mosquitto official repository", "https://github.com/eclipse-mosquitto/mosquitto"),
        ("[9]", "MQTT.js official repository", "https://github.com/mqttjs/MQTT.js"),
        ("[10]", "three.js official repository and GLTFLoader docs", "https://github.com/mrdoob/three.js"),
        ("[11]", "Vue 3 official repository", "https://github.com/vuejs/core"),
        ("[12]", "Express official repository", "https://github.com/expressjs/express"),
        ("[13]", "ThingsBoard official repository（架构参考，不作为本期平台底座）", "https://github.com/thingsboard/thingsboard"),
        ("[14]", "NIOSH, Carbon monoxide: Immediately Dangerous to Life or Health", "https://www.cdc.gov/niosh/npg/npgd0105.html"),
        ("[15]", "NIOSH, Methane safety reference", "https://www.cdc.gov/niosh/media/pdfs/2026/03/2006-127.pdf"),
        ("[16]", "项目参考资料.docx（用户提供，综合管廊传感与系统集成候选项）", "内部资料，不作为未经核验的强制参数"),
    ]
    add_table(doc, ["序号", "资料", "地址/说明"], refs, [700, 4500, 4160], font_size=7.8)

    add_heading(doc, "附录 E 已到货硬件台账与接入边界（2026-08-25）", 1)
    add_body(doc, "以下器件依据实物照片及项目组补充型号登记为已到货。未提供芯片丝印、工作电压、驱动芯片或有效电平的项目仍标记为“待上电核验”；未核验前不得按推测直接接入STM32或最终PCB。")
    add_table(doc, ["资产", "现有实物/识别", "项目建议用途", "接入与限制"], [
        ("H-01", "STM32F103RCT6开发板（已到货）", "现场控制器、采集与本地联动", "以开发板完成MVP；USART1调试，USART2接ESP8266；最终PCB保留SWD和同等接口。"),
        ("H-02", "WS2812B类5V RGB灯带（照片可见+5V/DIN/GND）", "管廊分区状态、报警与通行指示", "单线数据口；最终PCB加330Ω数据串联电阻、5V电源去耦，并评估3.3V到5V电平转换。"),
        ("H-03", "1.44寸OLED显示屏（实物接口：GND/VCC/SCL/SDA/RES/DC/CS/BLK）", "控制箱本地状态页、网络/报警/数值显示", "按实物接口预留SPI；上电确认驱动芯片、VCC、背光及初始化参数。它是本地辅助界面，不替代Web三维界面。"),
        ("H-04", "水位传感器（实物探针：S/+/-）", "接水盘泄漏触发", "可作真实积水演示的辅助传感器；电极长期浸水易电解腐蚀，建议周期供电采样，并保留浮球高水位作硬件保护。"),
        ("H-05", "土壤传感器", "接水盘辅助湿度/积水趋势验证", "上电确认是否带比较器及AO/DO接口；裸金属电极易腐蚀，不能单独作为安全联锁依据。"),
        ("H-06", "DHT11温湿度模块", "教室环境温湿度展示、基础联调", "单总线数字输入；精度和响应能力有限。管廊核心温湿度仍以SHT30/SHT3x为采购优先项。"),
        ("H-07", "SW-420常闭型震动传感器", "模拟外部振动/设备异常的扩展演示", "数字GPIO输入；台架确认常态/触发电平、消抖时间与阈值旋钮设置，不作为结构安全监测结论。"),
        ("H-08", "有源蜂鸣器模块（GND/I/O/VCC）", "本地声光报警", "GPIO驱动输入；核验高低电平有效方式与额定电压，急停状态下不允许依赖软件静音。"),
        ("H-09", "Risym 1路5V继电器模块", "风机或照明等低压负载通断", "继电器触点与MCU低压侧隔离；仅控制样品低压负载，感性负载加续流/吸收保护；先核验触发电平。"),
        ("H-10", "小型风机及IN-A/IN-B驱动板（具体芯片待核验）", "通风联动与风机故障场景", "先测额定电压、电流和驱动板逻辑；MCU不得直接带电机。需增加转速或电流反馈才可实现“风机失效”可靠判断。"),
        ("H-11", "HC-05蓝牙串口模块", "离线调试/手机近端维护扩展", "不纳入MVP核心链路；UART接入前按模块板级要求做3.3V电平适配，并确认供电和AT命令。核心通信仍采用ESP8266+MQTT。"),
        ("H-12", "单面万用PCB板（5×7cm）", "台架转接、小型接口板试制", "用于原型验证和焊接转接；最终交付仍应提供原理图、PCB、Gerber和BOM。"),
    ], [720, 2450, 2550, 3640], font_size=7.4)
    add_heading(doc, "附录 E.1 基于现有硬件的MVP接入优先级", 2)
    add_bullets(doc, [
        "立即接入：H-01控制器、H-04水位、H-06温湿度、H-08蜂鸣器、H-09继电器、H-10风机、H-02灯带和H-03显示屏；每种器件先单独台架验证再进入总线。",
        "作为扩展：H-07震动、H-11蓝牙和H-05土壤传感器。它们可丰富演示，但不应占用燃气管道泄漏、管廊渗水/积水、三维定位和运维闭环的关键工期。",
        "仍需采购：甲烷、CO、氧气专用传感器，SHT30/SHT3x（核心温湿度）、ESP8266、浮球高水位、烟感、高边接水盘、滴水器、吸水材料及隔离信号模拟盒。",
        "接线原则：所有GPIO先确认3.3V逻辑；传感器/执行器电源与MCU电源分区；风机、继电器和灯带的5V/12V电源按实际电流留余量，共地仅在控制侧单点连接。",
    ])

    # Keep the final approval statement and all six signature rows together on
    # a dedicated page instead of leaving only the last rows on a mostly blank
    # continuation page.
    doc.add_page_break()
    add_heading(doc, "批准与执行", 1)
    add_callout(doc, "执行结论", "本计划以9月10日可运行MVP和9月30日完整交付为双基线。任何成员发现技术、安全、交期或接口条件与计划不一致，应在当天提出并记录，不得在未评估影响的情况下静默改变方向。")
    add_table(doc, ["角色", "姓名", "确认内容", "日期/签字"], [
        ("项目组长", "车晨星", "范围、进度、资源和最终验收", ""),
        ("软件工程师", "王露帆", "平台、Web三维和软件交付", ""),
        ("运维工程师", "史润佳", "运维流程、规则、部署和SOP", ""),
        ("硬件开发工程师", "王为", "实体、硬件、PCB和安全结构", ""),
        ("测试工程师", "胡雨皓", "测试、缺陷、证据和验收", ""),
        ("嵌入式工程师", "闵昊", "固件、通信和现场联动", ""),
    ], [2100, 1800, 3860, 1600], font_size=9.2)

    doc.save(OUTPUT)
    print(OUTPUT)


if __name__ == "__main__":
    build()
