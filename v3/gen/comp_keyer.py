import numpy as np,cv2,subprocess,json,os
from PIL import Image
G="/opt/data/projects/Holodeck v3/gen/"
plate=cv2.cvtColor(cv2.imread(G+"plate-d72d79.png"),cv2.COLOR_BGR2RGB)
PH,PW=plate.shape[:2]
def key(rgb):
    f=rgb.astype(np.float32); r,g,b=f[...,0],f[...,1],f[...,2]
    gd=g-np.maximum(r,b)
    a=1-np.clip((gd-25)/(75-25),0,1)
    a=cv2.erode(a,np.ones((3,3),np.uint8))
    a=cv2.GaussianBlur(a,(0,0),0.8)
    # average despill: pull green down to the red/blue average
    lim=(r+b)/2+2
    g2=np.where(g>lim,lim,g)
    out=np.stack([r,g2,b],-1)
    return out,a
# read video frames
os.makedirs("vf",exist_ok=True)
subprocess.run(["ffmpeg","-v","error","-y","-i",G+"transition_stand_to_scorpion_wan3.mp4","vf/%03d.png"],check=True)
n=len(os.listdir("vf")); print("frames",n)
f0=cv2.cvtColor(cv2.imread("vf/001.png"),cv2.COLOR_BGR2RGB)
_,a0=key(f0); m=(a0>0.5).astype(np.uint8); m=cv2.morphologyEx(m,cv2.MORPH_OPEN,np.ones((5,5),np.uint8))
ys,xs=np.where(m>0); x0,x1,y0,y1=xs.min(),xs.max(),ys.min(),ys.max(); print("stand bbox in frame0",x0,x1,y0,y1)
sc=1377.0/(y1-y0); cx=(x0+x1)/2; print("scale",sc)
# target: feet bottom y=1531, centre x=681
tx=681-cx*sc; ty=1531-y1*sc
M=np.array([[sc,0,tx],[0,sc,ty]],np.float32)
def comp(rgb):
    fg,a=key(rgb)
    fgw=cv2.warpAffine(fg,M,(PW,PH),flags=cv2.INTER_LANCZOS4,borderValue=(0,0,0))
    aw=cv2.warpAffine(a,M,(PW,PH),flags=cv2.INTER_LINEAR,borderValue=0.0)
    al=aw[...,None]
    return np.clip(fgw*al+plate*(1-al),0,255).astype(np.uint8)
picks=[1,40,60,80,90,110,150]
tiles=[]
for p in picks:
    c=comp(cv2.cvtColor(cv2.imread(f"vf/{p:03d}.png"),cv2.COLOR_BGR2RGB))
    Image.fromarray(c).save(f"comp_{p:03d}.png"); tiles.append(c)
# crop sheet around figure area
cx0,cx1,cy0,cy1=250,1500,0,1584
crops=[cv2.resize(t[cy0:cy1,cx0:cx1],(500,634)) for t in tiles]
sheet=np.concatenate(crops[:4],1),np.concatenate(crops[4:]+[np.zeros_like(crops[0])],1)
Image.fromarray(np.concatenate(sheet,0)).save("comp_sheet_despill.jpg",quality=90)
# full-res side by side: original vs first/last composite
Image.fromarray(tiles[0]).resize((1408,792)).save("comp_first_despill.jpg",quality=90)
Image.fromarray(tiles[-1]).resize((1408,792)).save("comp_last_despill.jpg",quality=90)
# video
os.makedirs("cf",exist_ok=True)
for i in range(1,n+1):
    c=comp(cv2.cvtColor(cv2.imread(f"vf/{i:03d}.png"),cv2.COLOR_BGR2RGB))
    cv2.imwrite(f"cf/{i:03d}.jpg",cv2.cvtColor(cv2.resize(c,(1408,792),interpolation=cv2.INTER_AREA),cv2.COLOR_RGB2BGR),[cv2.IMWRITE_JPEG_QUALITY,92])
subprocess.run(["ffmpeg","-v","error","-y","-framerate","30","-i","cf/%03d.jpg","-c:v","libx264","-pix_fmt","yuv420p","-crf","18",G+"transition_on_plate_despill.mp4"],check=True)
print("done")
