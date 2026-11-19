import sys
from PIL import Image, ImageDraw, ImageFont
src=sys.argv[1]; out=sys.argv[2]; step=int(sys.argv[3]); box=[int(v) for v in sys.argv[4:8]] if len(sys.argv)>4 else None
im=Image.open(src).convert('RGB')
if box: im2=im.crop(box)
else: box=[0,0,*im.size]; im2=im
sc=max(1,int(round(1600/im2.width))) if im2.width<1600 else 1
if sc>1: im2=im2.resize((im2.width*sc,im2.height*sc),Image.LANCZOS)
d=ImageDraw.Draw(im2,'RGBA'); f=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf',20)
x0=(box[0]//step+1)*step
for x in range(x0,box[2],step):
    px=(x-box[0])*sc; d.line([(px,0),(px,im2.height)],fill=(255,255,0,110),width=1)
    d.rectangle([px+2,2,px+62,26],fill=(0,0,0,170)); d.text((px+4,3),str(x),fill=(255,255,0),font=f)
y0=(box[1]//step+1)*step
for y in range(y0,box[3],step):
    py=(y-box[1])*sc; d.line([(0,py),(im2.width,py)],fill=(0,255,255,110),width=1)
    d.rectangle([2,py+2,62,py+26],fill=(0,0,0,170)); d.text((4,py+3),str(y),fill=(0,255,255),font=f)
im2.save(out,quality=92)
