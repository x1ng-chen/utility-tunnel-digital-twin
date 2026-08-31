from PIL import Image, ImageDraw, ImageFont
from pathlib import Path
import math

OUT = Path(__file__).resolve().parents[1] / "model"
OUT.mkdir(exist_ok=True)
PNG = OUT / "utility-tunnel-ring-three-view.png"
SVG = OUT / "utility-tunnel-ring-three-view.svg"

W, H = 1800, 1300
img = Image.new("RGB", (W, H), "white")
d = ImageDraw.Draw(img)
font_path = r"C:\Windows\Fonts\msyh.ttc"
def font(size, bold=False):
    try:
        return ImageFont.truetype(font_path, size, index=1 if bold else 0)
    except Exception:
        return ImageFont.load_default()

F_TITLE, F_H = font(34, True), font(26, True)
F, F_SMALL, F_TINY = font(21), font(18), font(16)
INK = (28, 49, 68)
BLUE, CYAN, ORANGE, GREEN = (42, 105, 160), (44, 160, 175), (210, 120, 40), (49, 143, 86)
GRAY, WATER = (125, 137, 148), (110, 190, 225)

def txt(x, y, s, f=F, fill=INK, anchor=None):
    d.text((x, y), s, font=f, fill=fill, anchor=anchor)
def line(points, fill=INK, width=3):
    d.line(points, fill=fill, width=width)
def arrow(a, b, fill=INK, width=3, head=12):
    ang = math.atan2(b[1]-a[1], b[0]-a[0])
    line([a, b], fill, width)
    for off in (2.65, -2.65):
        p = (b[0] - head*math.cos(ang+off), b[1] - head*math.sin(ang+off))
        line([b, p], fill, width)
def dim_h(x1, x2, y, label, ext_y1=None, ext_y2=None):
    if ext_y1 is not None: line([(x1, ext_y1), (x1, y)], GRAY, 2)
    if ext_y2 is not None: line([(x2, ext_y2), (x2, y)], GRAY, 2)
    arrow((x1, y), (x2, y), GRAY, 2, 10); arrow((x2, y), (x1, y), GRAY, 2, 10)
    txt((x1+x2)//2, y-12, label, F_SMALL, GRAY, anchor="ms")
def dim_v(x, y1, y2, label, ext_x1=None, ext_x2=None):
    if ext_x1 is not None: line([(ext_x1, y1), (x, y1)], GRAY, 2)
    if ext_x2 is not None: line([(ext_x2, y2), (x, y2)], GRAY, 2)
    arrow((x, y1), (x, y2), GRAY, 2, 10); arrow((x, y2), (x, y1), GRAY, 2, 10)
    txt(x-12, (y1+y2)//2, label, F_SMALL, GRAY, anchor="rs")
def sensor(x, y, code, color, dx=0, dy=-34):
    d.ellipse((x-11, y-11, x+11, y+11), fill=color, outline=INK, width=2)
    txt(x+dx, y+dy, code, F_TINY, color)

txt(70, 42, "环形综合管廊数字孪生实体样品 · 三视图方案草图", F_TITLE)
txt(70, 87, "外形约 1000 × 500 × 420 mm；环形中心线、设备尺寸和传感器位置可参数化调整", F_SMALL, GRAY)
line([(70, 112), (1730, 112)], (180, 195, 205), 2)

# top view
txt(80, 145, "俯视图  TOP", F_H)
ox, oy, ow, oh = 150, 195, 930, 390
ix, iy, iw, ih = 310, 315, 610, 150
d.rounded_rectangle((ox, oy, ox+ow, oy+oh), radius=195, outline=INK, width=6, fill=(247, 251, 253))
d.rounded_rectangle((ix, iy, ix+iw, iy+ih), radius=75, outline=BLUE, width=5, fill="white")
txt(ix+iw//2, iy+ih//2, "中央可视空腔", F_H, BLUE, anchor="mm")
txt(ox+ow//2, oy+oh+40, "闭环环形通道（建议椭圆跑道形）", F, INK, anchor="mm")
line([(ox+250, oy+38), (ox+310, oy+oh-38)], (170, 185, 195), 2)
line([(ox+ow-300, oy+38), (ox+ow-250, oy+oh-38)], (170, 185, 195), 2)
txt(ox+130, oy+oh//2, "A区\n入口/环境", F, BLUE, anchor="mm")
txt(ox+ow//2, oy+oh-36, "B区  渗水/积水", F, CYAN, anchor="mm")
txt(ox+ow-135, oy+oh//2, "C区\n气体/风机", F, ORANGE, anchor="mm")
sensor(ox+145, oy+105, "DOOR-01", BLUE, -42, -34)
sensor(ox+ow//2, oy+oh-25, "SEEP-W01", CYAN, -48, 18)
sensor(ox+ow-105, oy+110, "GAS-01", ORANGE, 18, -33)
sensor(ox+ow-135, oy+oh-80, "FAN-01", ORANGE, 18, 12)
sensor(ox+ow-320, oy+oh-25, "CTRL-01", GREEN, -45, 18)
d.rounded_rectangle((ox+ow//2-75, oy+oh-85, ox+ow//2+75, oy+oh-45), radius=8, outline=CYAN, width=3, fill=(205, 239, 249))
txt(ox+ow//2, oy+oh-65, "透明水盘", F_TINY, CYAN, anchor="mm")
dim_h(ox, ox+ow, oy-42, "1000 mm", oy, oy)
dim_v(ox+ow+55, oy, oy+oh, "500 mm", ox+ow, ox+ow)

# front view
txt(1150, 145, "正视图  FRONT", F_H)
fx, fy, fw, fh = 1160, 195, 480, 390
d.rectangle((fx, fy, fx+fw, fy+fh), outline=INK, width=5, fill=(247, 251, 253))
d.rectangle((fx, fy+fh-72, fx+fw, fy+fh), outline=INK, width=3, fill=(215, 224, 230))
d.rectangle((fx+36, fy+55, fx+fw-36, fy+fh-72), outline=BLUE, width=4, fill="white")
d.rectangle((fx+64, fy+fh-135, fx+150, fy+fh-88), outline=GREEN, width=3, fill=(220, 239, 226))
txt(fx+107, fy+fh-112, "控制仓", F_TINY, GREEN, anchor="mm")
d.rectangle((fx+fw-160, fy+fh-145, fx+fw-72, fy+fh-88), outline=ORANGE, width=3, fill=(250, 232, 211))
txt(fx+fw-116, fy+fh-118, "风机", F_TINY, ORANGE, anchor="mm")
line([(fx+180, fy+fh-72), (fx+180, fy+fh-205)], GRAY, 3)
line([(fx+300, fy+fh-72), (fx+300, fy+fh-185)], GRAY, 3)
txt(fx+fw//2, fy+50, "4 mm透明亚克力盖板", F_SMALL, BLUE, anchor="mm")
dim_h(fx, fx+fw, fy-42, "1000 mm", fy, fy)
dim_v(fx+fw+48, fy, fy+fh, "420 mm", fx+fw, fx+fw)
dim_v(fx+fw+90, fy+fh-72, fy+fh, "80 mm底座", fx+fw, fx+fw)

# left view
txt(80, 710, "左视图  LEFT", F_H)
lx, ly, lw, lh = 180, 760, 390, 300
d.rectangle((lx, ly, lx+lw, ly+lh), outline=INK, width=5, fill=(247, 251, 253))
d.rectangle((lx, ly+lh-58, lx+lw, ly+lh), outline=INK, width=3, fill=(215, 224, 230))
d.rectangle((lx+32, ly+38, lx+lw-32, ly+lh-58), outline=BLUE, width=4, fill="white")
d.rounded_rectangle((lx+80, ly+86, lx+lw-80, ly+lh-100), radius=12, outline=GRAY, width=3)
txt(lx+lw//2, ly+150, "通道净空\n约 300 mm", F_SMALL, BLUE, anchor="mm")
sensor(lx+78, ly+112, "ENV-01", BLUE, -45, -36)
sensor(lx+lw-78, ly+112, "GAS-01", ORANGE, 15, -36)
dim_h(lx, lx+lw, ly-34, "500 mm", ly, ly)
dim_v(lx+lw+45, ly, ly+lh, "420 mm", lx+lw, lx+lw)
dim_v(lx+lw+82, ly+lh-58, ly+lh, "80 mm", lx+lw, lx+lw)

# notes
nx, ny = 720, 770
txt(nx, ny, "方案说明", F_H)
notes = [
    "1. 环形通道按椭圆跑道形生成，外包络约 1000 × 500 mm。",
    "2. A/B/C 三段分别承载环境、渗水、气体与设备场景。",
    "3. 传感器采用可拆卸安装座，位置和外形可按实物尺寸替换。",
    "4. 透明水盘布置在环路最低点；风机和气体传感器布置在 C 区。",
    "5. 本图为建模决策草图，最终加工尺寸需在建模前确认。",
]
for i, s in enumerate(notes): txt(nx, ny+52+i*38, s, F_SMALL, INK)
txt(nx, 1030, "图例", F_H)
legend = [(BLUE, "环境/门磁"), (CYAN, "渗水/水位"), (ORANGE, "气体/风机"), (GREEN, "控制/通信")]
for i, (c, s) in enumerate(legend):
    yy = 1080 + i*34
    d.ellipse((nx, yy-9, nx+18, yy+9), fill=c, outline=INK, width=1)
    txt(nx+30, yy, s, F_SMALL, INK, anchor="lm")
txt(70, 1232, "建议文件名：utility-tunnel-ring-three-view · 版本 V0.1 · 用于造型确认，不作为加工图", F_TINY, GRAY)

img.save(PNG, quality=95)
SVG.write_text(f'''<svg xmlns="http://www.w3.org/2000/svg" width="1800" height="1300" viewBox="0 0 1800 1300"><image href="{PNG.name}" x="0" y="0" width="1800" height="1300"/></svg>''', encoding="utf-8")
print(PNG)
print(SVG)
