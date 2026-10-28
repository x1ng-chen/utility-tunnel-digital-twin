"""Assemble genuine Blender renders into an explicitly labelled synthetic animation."""
import json
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont
ROOT=Path(__file__).resolve().parent
manifest=json.loads((ROOT/'previews/motion-example-manifest.json').read_text(encoding='utf-8'))
font=ImageFont.truetype('C:/Windows/Fonts/msyh.ttc',19)
small=ImageFont.truetype('C:/Windows/Fonts/msyh.ttc',14)
frames=[];durations=[]
for row in manifest['frames']:
    src=Image.open(row['file']).convert('RGB')
    frame=Image.new('RGB',(src.width,src.height+74),(17,25,34));frame.paste(src,(0,0))
    draw=ImageDraw.Draw(frame)
    text=('有供电 · 灯亮' if row['powered'] else '无供电 · 灯灭')+'    '+('叶片转动' if row['rotorTurning'] else '叶片停止')
    draw.text((18,src.height+7),text,font=font,fill=(239,245,247))
    draw.text((18,src.height+41),'效果演示 / 合成状态输入；非实物联调录像',font=small,fill=(164,181,194))
    frames.append(frame)
    durations.append(90 if row['rotorTurning'] else 200)
output=ROOT/'previews/power-and-motion-example.gif'
frames[0].save(output,save_all=True,append_images=frames[1:],duration=durations,loop=0,optimize=False)
print(json.dumps({'output':str(output),'frames':len(frames),'synthetic':True,'bytes':output.stat().st_size}))
