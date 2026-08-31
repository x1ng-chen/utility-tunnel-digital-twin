from PIL import Image, ImageDraw, ImageFont, ImageFilter
from pathlib import Path
import math

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "model"
OUT.mkdir(exist_ok=True)
PNG = OUT / "utility-tunnel-ring-three-view-v02.png"
SVG = OUT / "utility-tunnel-ring-three-view-v02.svg"

W, H = 2000, 1380
canvas = Image.new("RGB", (W, H), (244, 248, 251))
d = ImageDraw.Draw(canvas)

FONT = r"C:\Windows\Fonts\msyh.ttc"
def ft(size, bold=False):
    try:
        return ImageFont.truetype(FONT, size, index=1 if bold else 0)
    except Exception:
        return ImageFont.load_default()

T, H2, B, S, XS = ft(39, True), ft(27, True), ft(21), ft(18), ft(15)
NAVY, BLUE, CYAN, ORANGE, GREEN, RED = (20, 48, 72), (40, 107, 166), (35, 164, 184), (222, 133, 42), (49, 151, 94), (205, 69, 64)
GRAY, MID, PALE, WHITE = (109, 126, 141), (177, 192, 203), (229, 239, 246), (255, 255, 255)

def text(x, y, value, font=B, color=NAVY, anchor=None):
    d.text((x, y), value, font=font, fill=color, anchor=anchor, spacing=4)
def stroke(points, color=NAVY, width=3):
    d.line(points, fill=color, width=width, joint="curve")
def dot(x, y, color, label=None, label_pos=(15, -29)):
    d.ellipse((x-12, y-12, x+12, y+12), fill=WHITE, outline=color, width=4)
    d.ellipse((x-5, y-5, x+5, y+5), fill=color)
    if label:
        text(x+label_pos[0], y+label_pos[1], label, XS, color)
def leader(a, b, label, color, align="left"):
    stroke([a, b], color, 2)
    d.ellipse((a[0]-3, a[1]-3, a[0]+3, a[1]+3), fill=color)
    text(b[0] + (10 if align == "left" else -10), b[1]-2, label, XS, color, anchor="lm" if align == "left" else "rm")
def arrow(a, b, color=GRAY, width=2, head=9):
    stroke([a, b], color, width)
    ang = math.atan2(b[1]-a[1], b[0]-a[0])
    for off in (2.6, -2.6):
        p = (b[0] - head*math.cos(ang+off), b[1] - head*math.sin(ang+off))
        stroke([b, p], color, width)
def dim_h(x1, x2, y, label, yref):
    stroke([(x1, yref), (x1, y)], MID, 2); stroke([(x2, yref), (x2, y)], MID, 2)
    arrow((x1, y), (x2, y), MID); arrow((x2, y), (x1, y), MID)
    text((x1+x2)//2, y-11, label, S, GRAY, "ms")
def dim_v(x, y1, y2, label, xref):
    stroke([(xref, y1), (x, y1)], MID, 2); stroke([(xref, y2), (x, y2)], MID, 2)
    arrow((x, y1), (x, y2), MID); arrow((x, y2), (x, y1), MID)
    text(x-12, (y1+y2)//2, label, S, GRAY, "rs")
def card(box, radius=22):
    x1,y1,x2,y2 = box
    d.rounded_rectangle((x1+6,y1+8,x2+6,y2+8), radius=radius, fill=(229, 237, 242))
    d.rounded_rectangle(box, radius=radius, fill=WHITE, outline=(213,225,232), width=2)

# Background and title.
d.rectangle((0,0,W,154), fill=WHITE)
d.rectangle((0,150,W,154), fill=BLUE)
text(65, 41, "环形综合管廊数字孪生实体样品", T)
text(65, 94, "多气体检测布置 · 三视图方案 V0.2  |  约 1000 × 500 × 420 mm  |  造型确认稿", S, GRAY)
text(1900, 70, "UT-CONCEPT-02", S, BLUE, "rm")

# Main top view card.
card((50, 190, 1230, 770))
text(85, 220, "俯视图  TOP VIEW", H2)
text(85, 256, "椭圆闭环通道：用颜色定义场景分区，用独立点位定义数据来源", XS, GRAY)
ox, oy, ow, oh = 145, 320, 920, 360
ix, iy, iw, ih = 328, 426, 554, 148
d.rounded_rectangle((ox,oy,ox+ow,oy+oh), radius=180, fill=(237,245,249), outline=NAVY, width=6)
# zone bands inside track, then central void over it.
d.pieslice((ox,oy,ox+360,oy+oh), 90, 270, fill=(222,235,247), outline=None)
d.rectangle((ox+180,oy,ox+ow-180,oy+oh), fill=(235,242,247))
d.pieslice((ox+ow-360,oy,ox+ow,oy+oh), 270, 90, fill=(250,235,214), outline=None)
d.rounded_rectangle((ix,iy,ix+iw,iy+ih), radius=74, fill=WHITE, outline=BLUE, width=5)
text(ix+iw//2, iy+ih//2-10, "中央可视空腔", H2, BLUE, "mm")
text(ix+iw//2, iy+ih//2+28, "可放置可视灯带 / 走线槽", XS, GRAY, "mm")
# discrete B-zone water tray.
d.rounded_rectangle((536, 608, 683, 648), radius=9, fill=(204,240,248), outline=CYAN, width=3)
text(610, 628, "水盘", XS, CYAN, "mm")
# zone names
text(238, 495, "A 区\n入口 · 环境", H2, BLUE, "mm")
text(610, 655, "B 区  渗水 · 水位", H2, CYAN, "mm")
text(966, 495, "C 区\n气体 · 通风", H2, ORANGE, "mm")
# sensors - all labels have concise asset codes and leaders.
dot(255, 391, BLUE); leader((255,391),(165,338),"ENV-01  温湿度",BLUE)
dot(302, 545, BLUE); leader((302,545),(160,592),"DOOR-01  门磁",BLUE)
dot(515, 635, CYAN); leader((515,635),(420,708),"SEEP-W01  水浸",CYAN)
dot(706, 635, CYAN); leader((706,635),(766,708),"LEVEL-01  高水位",CYAN)
dot(920, 360, ORANGE); leader((920,360),(1000,292),"GAS-CH4-01  甲烷",ORANGE)
dot(1002, 455, RED); leader((1002,455),(1115,430),"SMOKE-01  烟雾",RED)
dot(989, 564, ORANGE); leader((989,564),(1112,604),"GAS-CO-01  一氧化碳",ORANGE)
dot(853, 641, GREEN); leader((853,641),(915,706),"GAS-O2-01  氧气",GREEN)
dot(945, 623, ORANGE); leader((945,623),(1080,695),"FAN-01  排风",ORANGE)
dot(744, 658, GREEN); leader((744,658),(745,745),"CTRL-01  控制仓",GREEN)
dim_h(ox, ox+ow, 294, "1000 mm", oy)
dim_v(1114, oy, oy+oh, "500 mm", ox+ow)

# Front elevation card.
card((1280, 190, 1950, 770))
text(1315, 220, "正视图  FRONT", H2)
text(1315, 256, "用高度表达气体分层与维护带", XS, GRAY)
fx, fy, fw, fh = 1340, 330, 500, 355
d.rounded_rectangle((fx,fy,fx+fw,fy+fh), 10, fill=(246,250,252), outline=NAVY, width=5)
d.rectangle((fx,fy+fh-68,fx+fw,fy+fh), fill=(220,229,235), outline=NAVY, width=3)
d.rounded_rectangle((fx+35,fy+45,fx+fw-35,fy+fh-68), 8, fill=WHITE, outline=BLUE, width=4)
# layer guide bands
d.rectangle((fx+45, fy+55, fx+fw-45, fy+116), fill=(255,244,229))
d.rectangle((fx+45, fy+117, fx+fw-45, fy+205), fill=(237,247,247))
d.rectangle((fx+45, fy+206, fx+fw-45, fy+fh-78), fill=(240,248,244))
text(fx+55, fy+69, "顶部检测带：CH₄ + 烟雾", S, ORANGE)
text(fx+55, fy+143, "中部呼吸带：CO + O₂", S, GREEN)
text(fx+55, fy+235, "底部风险带：水浸 + 高水位", S, CYAN)
# sensor mount icons / leakage and fan
dot(fx+375, fy+89, ORANGE, "CH₄")
dot(fx+315, fy+89, RED, "烟雾")
dot(fx+185, fy+164, ORANGE, "CO")
dot(fx+265, fy+164, GREEN, "O₂")
dot(fx+92, fy+250, CYAN, "水浸")
d.ellipse((fx+400,fy+185,fx+455,fy+240), outline=ORANGE, width=4)
for a in range(0, 360, 90):
    x = fx+427 + int(18*math.cos(math.radians(a)))
    y = fy+212 + int(18*math.sin(math.radians(a)))
    stroke([(fx+427,fy+212),(x,y)], ORANGE, 3)
text(fx+427, fy+260, "FAN-01", XS, ORANGE, "mm")
dim_h(fx, fx+fw, fy-30, "1000 mm", fy)
dim_v(fx+fw+37, fy, fy+fh, "420 mm", fx+fw)
dim_v(fx+fw+80, fy+fh-68, fy+fh, "80 mm 底座", fx+fw)

# Left/cross-section card.
card((50, 815, 700, 1280))
text(85, 845, "左视图  LEFT", H2)
text(85, 881, "通道截面与设备检修余量", XS, GRAY)
lx, ly, lw, lh = 130, 940, 430, 280
d.rounded_rectangle((lx,ly,lx+lw,ly+lh), 10, fill=(246,250,252), outline=NAVY, width=5)
d.rectangle((lx,ly+lh-60,lx+lw,ly+lh), fill=(220,229,235), outline=NAVY, width=3)
d.rounded_rectangle((lx+38,ly+42,lx+lw-38,ly+lh-60), 8, fill=WHITE, outline=BLUE, width=4)
d.rounded_rectangle((lx+104,ly+90,lx+lw-104,ly+lh-104), 17, fill=(247,250,252), outline=GRAY, width=3)
text(lx+lw//2, ly+150, "环形通道净空\n约 300 mm", S, BLUE, "mm")
dot(lx+95, ly+116, ORANGE); leader((lx+95,ly+116),(70,1010),"CH₄ 顶部",ORANGE,"right")
dot(lx+lw-92, ly+174, GREEN); leader((lx+lw-92,ly+174),(606,1062),"O₂ / CO 中部",GREEN)
dot(lx+lw//2, ly+lh-85, CYAN); leader((lx+lw//2,ly+lh-85),(340,1240),"水浸最低点",CYAN)
dim_h(lx, lx+lw, ly-28, "500 mm", ly)
dim_v(lx+lw+34, ly, ly+lh, "420 mm", lx+lw)

# Layout and integration panel.
card((750, 815, 1950, 1280))
text(790, 845, "传感器与数据采集配置", H2)
text(790, 881, "推荐第一版采用 3 气体 + 烟雾 + 环境 + 水浸的组合；所有点位保留独立 GLB mesh。", XS, GRAY)
rows = [
    (ORANGE, "GAS-CH4-01", "甲烷 CH₄ / 可燃气", "C区顶部，泄漏点 LEAK-G01 上方，距风机直吹区留出间隔", "顶部积聚趋势 + 泄漏源优先"),
    (ORANGE, "GAS-CO-01", "一氧化碳 CO", "C区中部靠近管道与回风侧", "吸入风险监测，避免贴近排风口"),
    (GREEN, "GAS-O2-01", "氧气 O₂", "C区中部、与 CO 同一维护高度但独立 mesh", "氧气异常的呼吸带监测"),
    (RED, "SMOKE-01", "烟雾", "环路最高处，远离进/排风直吹", "热烟上升与早期火情展示"),
    (CYAN, "SEEP-W01 / LEVEL-01", "水浸 / 高水位", "B区最低点的透明水盘内", "渗水和积水两级联动"),
    (BLUE, "ENV-01", "温湿度", "A区入口内侧、中部高度", "环境基线与参观可视性"),
]
x0, y0 = 790, 925
col = [0, 205, 430, 780]
headers = ["资产编号", "采集对象", "建议位置", "建模 / 交互重点"]
for i, h in enumerate(headers): text(x0+col[i], y0, h, XS, GRAY)
stroke([(x0,y0+28),(1900,y0+28)], MID, 2)
for n, (color, code, target, loc, reason) in enumerate(rows):
    yy = y0+54+n*48
    d.ellipse((x0,yy-7,x0+14,yy+7),fill=color)
    text(x0+25,yy,code,XS,NAVY,"lm")
    text(x0+col[1],yy,target,XS,NAVY,"lm")
    text(x0+col[2],yy,loc,XS,NAVY,"lm")
    text(x0+col[3],yy,reason,XS,NAVY,"lm")
    stroke([(x0,yy+23),(1900,yy+23)], (229,236,241), 1)

text(790, 1240, "注：此布局服务于低压、隔离信号模拟的演示样机；真实场地必须按传感器说明书、通风条件和适用规范复核。", XS, RED)

canvas.save(PNG, quality=96)
SVG.write_text(f'<svg xmlns="http://www.w3.org/2000/svg" width="2000" height="1380" viewBox="0 0 2000 1380"><image href="{PNG.name}" x="0" y="0" width="2000" height="1380"/></svg>', encoding="utf-8")
print(PNG)
print(SVG)
