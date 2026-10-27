"""Generate the small project-owned UI glyph table; no full font is distributed."""
from pathlib import Path
import json
import re
from PIL import Image,ImageDraw,ImageFont

ROOT=Path(__file__).resolve().parents[1]
TEXT='主控正常报警实时过期等待网关数据缺失当前视图风机转速功率电流温湿度水位原始量存疑锁存确认取消移动按键选择节点测点动作类型数值输出已应用未验证拒绝超时本地保护自动恢复下发状态菜单通信'

def main():
    font_path=next((p for p in (Path('C:/Windows/Fonts/simsun.ttc'),Path('C:/Windows/Fonts/msyh.ttc'),Path('/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc')) if p.exists()),None)
    if not font_path: raise SystemExit('Chinese font unavailable. The checked-in glyph header remains usable.')
    font=ImageFont.truetype(str(font_path),16)
    lines=['/* Generated sparse 16x16 UI glyphs. Regenerate with tools/generate_ui_font.py. */',
        '#ifndef UT_UI_FONT_H','#define UT_UI_FONT_H','#include <stdint.h>',
        'typedef struct {uint16_t codepoint;uint8_t bitmap[32];} UtUiGlyph;',
        'static const UtUiGlyph UT_UI_GLYPHS[]={']
    source_text=''.join((ROOT/'Core/Src'/name).read_text(encoding='utf-8') for name in ('screen.c','menu.c'))
    literals=''.join(re.findall(r'"(?:[^"\\]|\\.)*"',source_text))
    characters=sorted(set(TEXT)|{ch for ch in literals if '\u4e00'<=ch<='\u9fff'})
    for ch in characters:
        image=Image.new('1',(16,16),0);draw=ImageDraw.Draw(image);box=draw.textbbox((0,0),ch,font=font)
        draw.text(((16-box[2]+box[0])//2-box[0],(16-box[3]+box[1])//2-box[1]),ch,font=font,fill=1)
        data=[sum((0x80>>bit) if image.getpixel((block*8+bit,y)) else 0 for bit in range(8)) for y in range(16) for block in range(2)]
        lines.append('  {0x%04X,{%s}}, /* %s */'%(ord(ch),','.join('0x%02X'%b for b in data),ch))
    lines+=['};','#define UT_UI_GLYPH_COUNT (sizeof UT_UI_GLYPHS/sizeof UT_UI_GLYPHS[0])','#endif','']
    (ROOT/'Core/Inc/ui_zh_font.h').write_text('\n'.join(lines),encoding='utf-8')
    print(json.dumps({'glyphs':len(characters),'output':'Core/Inc/ui_zh_font.h'}))

if __name__=='__main__':main()
