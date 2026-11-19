import numpy as np, cv2, math
from PIL import Image, ImageDraw, ImageFont
W,H=2816,1584
WARM=(1.0,0.70,0.36); COOL=(0.50,0.84,1.0); IVORY=(1.0,0.95,0.84); WHITE=(1,1,1)
MONO='/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf'; SANS='/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'

def grade(im):
    a=np.asarray(im).astype(np.float32)/255
    a=a**1.06
    a=a+0.42*(a*a*(3-2*a)-a)*1.0            # S-curve
    lum=a.mean(2,keepdims=True)
    a=lum+(a-lum)*1.22                        # saturation
    sh=np.clip(1-lum*3,0,1); hi=np.clip((lum-0.55)*2.2,0,1)
    a=a+sh*np.array([-0.012,0.004,0.02])+hi*np.array([0.03,0.012,-0.02])
    yy,xx=np.mgrid[0:H,0:W].astype(np.float32)
    v=((xx-W/2)/(W*0.62))**2+((yy-H*0.46)/(H*0.72))**2
    a=a*(1-0.42*np.clip(v,0,1)**1.4)[...,None]
    return np.clip(a,0,1)

class Layer:
    def __init__(s): s.c=np.zeros((H,W,3),np.uint8)
    def col(s,c,i): return tuple(int(min(255,255*v*i)) for v in c)
    def line(s,pts,c,i=1,w=2):
        p=np.round(np.array(pts)*8).astype(np.int32).reshape(-1,1,2)
        cv2.polylines(s.c,[p],False,s.col(c,i),w,cv2.LINE_AA,3)
    def dot(s,x,y,r,c,i=1):
        cv2.circle(s.c,(int(round(x*8)),int(round(y*8))),int(round(r*8)),s.col(c,i),-1,cv2.LINE_AA,3)
    def ring(s,x,y,r,c,i=1,w=1):
        cv2.circle(s.c,(int(round(x*8)),int(round(y*8))),int(round(r*8)),s.col(c,i),w,cv2.LINE_AA,3)
    def glow(s,mask=None,k=(0.9,0.6,0.38)):
        f=s.c.astype(np.float32)/255
        if mask is not None: f=f*mask[...,None]
        return f+k[0]*cv2.GaussianBlur(f,(0,0),3.5)+k[1]*cv2.GaussianBlur(f,(0,0),13)+k[2]*cv2.GaussianBlur(f,(0,0),42)

def bez(p0,p1,p2,p3,n=60):
    t=np.linspace(0,1,n)[:,None]; p0,p1,p2,p3=map(np.array,(p0,p1,p2,p3))
    return (1-t)**3*p0+3*(1-t)**2*t*p1+3*(1-t)*t*t*p2+t**3*p3
def smooth(pts,n=160):
    from scipy.interpolate import splprep,splev
    p=np.array(pts,float); tck,_=splprep([p[:,0],p[:,1]],s=0,k=min(3,len(p)-1))
    u=np.linspace(0,1,n); x,y=splev(u,tck); return np.stack([x,y],1)

# ---------- neural-net sculptures ----------
def net_lana(rng):
    N=[];E=[]
    def cloud(n,r0,r1):
        out=[]
        for _ in range(n):
            a=rng.uniform(0,2*math.pi); r=rng.uniform(r0,r1)**0.8
            out.append((1.18*r*math.cos(a),0.88*r*math.sin(a)))
        return out
    core=cloud(13,0.02,0.26); mid=cloud(28,0.34,0.6); outer=cloud(36,0.68,1.0)
    N=core+mid+outer
    def near(p,pool,off,k):
        d=sorted(range(len(pool)),key=lambda j:(pool[j][0]-p[0])**2+(pool[j][1]-p[1])**2)[:k]; return [off+j for j in d]
    for i,p in enumerate(core):
        for j in near(p,core,0,3)[1:]: E.append((i,j))
    for i,p in enumerate(mid):
        for j in near(p,core,0,2): E.append((13+i,j))
        E.append((13+i,near(p,mid,13,2)[1]))
    for i,p in enumerate(outer):
        for j in near(p,mid,13,2): E.append((41+i,j))
    T=[]
    for i in rng.choice(36,13,replace=False):
        p=np.array(outer[i]); d=p/np.linalg.norm(p); L=rng.uniform(0.45,1.15); n=np.array([-d[1],d[0]])*rng.uniform(-0.5,0.5)
        T.append((41+i,bez(p,p+d*L*0.4+n*0.2,p+d*L*0.8+n*0.9,p+d*L+n*1.2,30)))
    return N,E,T
def net_mila(rng):
    counts=[1,3,5,7,4,3,4,7,5,3,1]; prof=[0,.22,.42,.62,.34,.18,.34,.62,.42,.22,0]
    N=[];rows=[]
    for li,(c,w) in enumerate(zip(counts,prof)):
        y=-1+2*li/(len(counts)-1); row=[]
        for k in range(c):
            x=0 if c==1 else -w+2*w*k/(c-1)
            row.append(len(N)); N.append((x*0.95,y*1.05+0.05*math.cos(x*5)))
        rows.append(row)
    E=[]
    for a,b in zip(rows,rows[1:]):
        for i in a:
            d=sorted(b,key=lambda j:abs(N[j][0]-N[i][0]))[:2]
            for j in d: E.append((i,j))
        for j in b:
            E.append((min(a,key=lambda i:abs(N[i][0]-N[j][0])),j))
    T=[]
    for sx in (-1,1):
        p=np.array(N[rows[3][0 if sx<0 else -1]]); T.append((0,bez(p,p+[sx*.35,-.1],p+[sx*.6,.25],p+[sx*.55,.75],30)))
        p=np.array(N[rows[7][0 if sx<0 else -1]]); T.append((0,bez(p,p+[sx*.3,.1],p+[sx*.5,.5],p+[sx*.42,.95],30)))
    return N,E,T
def net_fan(rng):
    N=[(0,0.9)];E=[];prev=[0]
    for li,c in enumerate([3,5,6]):
        row=[]
        for k in range(c):
            a=math.radians(-90+(k-(c-1)/2)*(26-li*4)); r=0.55+li*0.5
            row.append(len(N)); N.append((r*math.cos(a)*0.9,0.9+r*math.sin(a)))
        for j in row:
            for i in sorted(prev,key=lambda i:abs(N[i][0]-N[j][0]))[:2]: E.append((i,j))
        prev=row
    return N,E,[]
def net_helix(rng):
    N=[];E=[]
    for k in range(9):
        y=-1+2*k/8; ph=k*0.8
        N.append((0.45*math.sin(ph),y)); N.append((-0.45*math.sin(ph),y))
        E.append((2*k,2*k+1))
        if k: E+= [(2*k-2,2*k),(2*k-1,2*k+1)]
    return N,E,[]
def net_ring(rng):
    N=[(0,0)];E=[]
    for k in range(9):
        a=k*2*math.pi/9; N.append((math.cos(a),math.sin(a)*0.8)); E.append((0,k+1))
    for k in range(9): E.append((k+1,(k+1)%9+1))
    for k in range(0,9,3):
        a=k*2*math.pi/9+0.3; N.append((1.45*math.cos(a),1.2*math.sin(a))); E.append((k+1,len(N)-1))
    return N,E,[]
def net_derpy(rng):
    # lopsided little clump: two mismatched eyes, one node that wandered off, a tendril much too long for it
    N=[(-0.1,0.5),(0.45,0.62),(-0.6,0.35),(0.15,0.05),(-0.35,-0.05),(0.75,0.2),(0.3,0.95),(-0.3,0.98),
       (-0.42,-0.55),(0.38,-0.48),(1.55,-0.95)]
    E=[(0,1),(0,2),(0,3),(0,4),(1,5),(1,6),(0,7),(2,4),(3,5),(3,9),(4,8),(3,4),(6,7)]
    T=[(5,np.array([[0.75,0.2],[1.05,0.05],[1.2,-0.25],[1.32,-0.6],[1.55,-0.95]])),          # wobbly leash to the stray node
       (2,bez((-0.6,0.35),(-1.3,0.2),(-1.5,1.0),(-1.0,1.25),30)),
       (0,bez((-1.0,1.25),(-0.7,1.4),(-0.9,1.6),(-1.25,1.5),20))]
    return N,E,T

def draw_net(L,kind,cx,cy,sc,col,level,seed,rot=0,lit=0.25,eyes=False):
    rng=np.random.default_rng(seed)
    N,E,T={'lana':net_lana,'mila':net_mila,'fan':net_fan,'helix':net_helix,'ring':net_ring,'derpy':net_derpy}[kind](rng)
    c,s=math.cos(rot),math.sin(rot)
    tr=lambda p:(cx+sc*(p[0]*c-p[1]*s),cy+sc*(p[0]*s+p[1]*c))
    P=[tr(p) for p in N]
    for a,b in E: L.line([P[a],P[b]],col,0.56*level,1)
    ends=[]
    for _,t in T:
        tp=[tr(p) for p in t]; L.line(tp,col,0.42*level,1); L.dot(*tp[-1],2.2,col,0.8*level); ends.append(tp[-1])
    big=kind in('lana','mila')
    for i,p in enumerate(P):
        on=rng.random()<lit
        r=(3.4 if big else 2.8)*(1.35 if on else 1)*(1.25 if (kind=='lana' and i<13) else 1)
        L.dot(*p,r,WHITE if on else col,(1.0 if on else 0.62)*level)
    if eyes:
        for i,(r,dx,dy) in zip((8,9),((12,3,-2),(8,-2,3))):
            L.ring(*P[i],r,col,0.95*level,2); L.dot(P[i][0]+dx,P[i][1]+dy,3.2,WHITE,1.0*level)
    return P,ends

def text_layer(items):
    im=Image.new('RGB',(W,H)); d=ImageDraw.Draw(im)
    for x,y,txt,size,col,inten,anchor,font in items:
        f=ImageFont.truetype(font,size)
        d.multiline_text((x,y),txt,font=f,fill=tuple(int(255*v*inten) for v in col),anchor=anchor,align='center' if anchor[0]=='m' else 'left',spacing=6)
    return np.asarray(im).astype(np.float32)/255

LC={'L':[[(1113,1110),(1080,1218),(1017,1304),(946,1342),(815,1337),(574,1332),(285,1331),(0,1327)],
         [(1097,1134),(1052,1250),(995,1345),(922,1384),(833,1391),(605,1362),(308,1352),(0,1350)],
         [(1179,1198),(1131,1313),(1068,1386),(976,1408),(850,1394),(610,1371),(301,1361),(0,1366)]],
    'R':[[(1694,1114),(1730,1229),(1788,1315),(1858,1347),(1982,1337),(2228,1335),(2510,1333),(2815,1339)],
         [(1716,1125),(1763,1254),(1825,1352),(1894,1384),(1984,1389),(2217,1362),(2514,1350),(2815,1357)],
         [(1625,1212),(1675,1323),(1759,1393),(1830,1411),(1950,1393),(2206,1370),(2510,1354),(2815,1369)]]}
ARC_L=[(337,1345),(540,1319),(788,1300),(1007,1290)]; ARC_R=[(1791,1290),(2015,1306),(2249,1327),(2475,1360)]
HC=(1406,434); HR=302

def render(active,annot=False):
    base=grade(Image.open('source.jpg').convert('RGB'))
    q=1.0 if active else 0.5
    F=Layer(); A=Layer()   # F = floor substrate (masked by legs), A = everything else
    # --- optical substrate along the existing cable routes ---
    for side,col in (('L',WARM),('R',COOL)):
        for k,c in enumerate(LC[side]):
            s=smooth(c); F.line(s,col,(0.55 if k==0 else 0.36)*q,2 if k==0 else 1)
            for j in range(12,len(s)-6,17+5*k):      # junction beads + tiny branch stubs
                F.dot(*s[j],1.7,col,0.5*q)
                if j%2==0:
                    d=s[j+1]-s[j]; n=np.array([-d[1],d[0]])/ (np.linalg.norm(d)+1e-6)
                    e=s[j]+n*(14+6*k)*(1 if k!=1 else -1)+d*2; F.line([s[j],e],col,0.4*q,1); F.dot(*e,1.6,col,0.6*q)
        arc=smooth(ARC_L if side=='L' else ARC_R,80); F.line(arc,IVORY,0.26*q,1)
    # --- MCP prisms on the platform arc ---
    prisms=[(540,1319),(1007,1290),(337,1345),(1791,1290),(2249,1327),(2475,1360)]
    for i,(x,y) in enumerate(prisms):
        on=active and i==1
        d=np.array([(0,-17),(11,0),(0,9),(-11,0),(0,-17)])+(x,y-6)
        F.line(d,IVORY,1.0 if on else 0.5*q+0.12,2 if on else 1); F.line([d[0],d[2]],IVORY,0.5 if on else 0.22,1)
        if on:
            for ang,cc in ((-62,(1,0.55,0.4)),(-90,(1,0.95,0.7)),(-118,(0.5,0.85,1))):
                a=math.radians(ang); F.line([(x,y-24),(x+30*math.cos(a),y-24+30*math.sin(a))],cc,0.5,1)
    # --- Hindsight: memory drum on the halo ---
    rng=np.random.default_rng(7)
    for deg in np.arange(142,400,1.6):
        a=math.radians(deg); v=rng.random()
        r0=HR+12; r1=r0+6+16*v**2
        A.line([(HC[0]+r0*math.cos(a),HC[1]+r0*math.sin(a)),(HC[0]+r1*math.cos(a),HC[1]+r1*math.sin(a))],IVORY,(0.2+0.5*v)*q,1)
    arc=[(HC[0]+(HR+8)*math.cos(math.radians(d)),HC[1]+(HR+8)*math.sin(math.radians(d))) for d in np.arange(142,400,1)]
    A.line(arc,IVORY,0.3*q,1)
    if active:   # one stratum being written
        seg=[(HC[0]+(HR+8)*math.cos(math.radians(d)),HC[1]+(HR+8)*math.sin(math.radians(d))) for d in np.arange(205,236,1)]
        A.line(seg,IVORY,1.0,3)
        for deg in np.arange(205,236,1.6):
            a=math.radians(deg); A.line([(HC[0]+(HR+12)*math.cos(a),HC[1]+(HR+12)*math.sin(a)),(HC[0]+(HR+34)*math.cos(a),HC[1]+(HR+34)*math.sin(a))],IVORY,0.95,1)
    # --- the networks ---
    PL,eL=draw_net(A,'lana',395,205,150,WARM,1.0 if active else 0.55,11,lit=0.42 if active else 0.1)
    PM,eM=draw_net(A,'mila',2420,210,150,COOL,0.75 if active else 0.6,5,lit=0.1)
    staff=[('fan',322,505,46,WARM,3,0,0.1,0.5),('helix',505,930,52,WARM,4,0.15,0.1,0.5),('ring',318,850,38,WARM,6,0,0.1,0.5),
           ('ring',2480,495,40,COOL,8,0.3,0.1,0.5),('fan',2318,935,44,COOL,9,0,0.1,0.5)]
    SP=[]
    for kind,x,y,sc,col,seed,rot,lit,lv in staff:
        P,_=draw_net(A,kind,x,y,sc,col,lv*(1 if active else 0.9),seed,rot,lit); SP.append((x,y,sc))
    dl=1.0 if active else 0.55
    PD,eD=draw_net(A,'derpy',2575,1215,50,COOL,dl,2,rot=math.radians(-13),lit=0.6 if active else 0.15,eyes=True)
    # --- tendrils into the architecture / substrate ---
    def tend(a,c1,c2,b,col,i,layer=A,w=1): layer.line(bez(a,c1,c2,b,80),col,i*q,w)
    tend((330,330),(380,520),(445,700),(442,1100),WARM,0.5); tend((442,1100),(442,1220),(470,1300),(540,1332),WARM,0.5)
    tend((322,560),(330,640),(400,700),(441,820),WARM,0.34); tend((318,892),(330,960),(400,1000),(441,1060),WARM,0.34)
    tend((505,985),(500,1100),(520,1250),(574,1332),WARM,0.34)
    tend((2485,330),(2440,520),(2362,700),(2362,1100),COOL,0.5); tend((2362,1100),(2362,1220),(2330,1300),(2260,1335),COOL,0.5)
    tend((2480,540),(2470,640),(2400,720),(2363,830),COOL,0.34); tend((2318,985),(2318,1100),(2300,1250),(2228,1335),COOL,0.34)
    tend(eD[-1],(2470,1300),(2440,1330),(2400,1336),COOL,0.5)
    # ceiling runs: each sister's net to the memory drum
    tend((560,150),(820,40),(1150,30),(1396,118),WARM,0.3); tend((2330,120),(2050,30),(1680,30),(1416,118),COOL,0.3)
    # chair = the empty seat (Martin's input): footplate lip
    A.line([(1262,1481),(1546,1481)],IVORY,0.9 if active else 0.22,2)
    texts=[]
    if active:
        # Lana thinking: thread from net to glyph cloud above her head
        tend((560,235),(600,200),(610,150),(640,112),WARM,0.5)
        texts.append((728,58,"⣾⣽⣻⢿⡿⣟⣯⣷",27,WARM,0.95,'mm',SANS)); texts.append((728,94,"( ˘ω˘ ) weaving…",25,WARM,0.95,'mm',MONO)); texts.append((728,128,"⠁⠂⠄⡀⢀⠠⠐⠈",27,WARM,0.7,'mm',SANS))
        # placement B (sternum) shown on Mila for comparison
        texts.append((2063,436,"⠋⠙⠹⠸",23,COOL,0.9,'mm',SANS)); texts.append((2063,464,"listening",21,COOL,0.9,'mm',MONO))
        # ONE crisp point of light travelling Lana -> Mila along the floor run
        s=smooth(LC['L'][0]); px,py=s[52]
        F.dot(px,py,7.5,WHITE,1.0) 
    lm=np.ones((H,W),np.float32)
    for x0,x1 in ((655,845),(1985,2185)): cv2.rectangle(lm,(x0,1120),(x1,1560),0,-1)
    cv2.rectangle(lm,(1230,1100),(1575,1500),0.0,-1)
    lm=cv2.GaussianBlur(lm,(0,0),10)
    g=F.glow(lm)+A.glow()
    if texts:
        t=text_layer(texts); g=g+t+0.8*cv2.GaussianBlur(t,(0,0),3)+0.5*cv2.GaussianBlur(t,(0,0),12)
    out=1-(1-base)*(1-np.clip(g,0,1))
    img=Image.fromarray((np.clip(out,0,1)*255).astype(np.uint8))
    if annot:
        d=ImageDraw.Draw(img,'RGBA'); f=ImageFont.truetype(SANS,24)
        labs=[(40,395,"LANA'S NET · largest, densest,\nmost tendrils",(395,330)),(2150,395,"MILA'S NET · poised,\nhourglass lattice",(2420,360)),
              (60,600,"staff nets (count illustrative)",(300,540)),(2380,1420,"THE DERPY ONE\n(Mila's staff · working)",(2575,1270)),
              (1150,40,"HINDSIGHT · memory drum\nbright arc = a write in progress",(1215,205)),
              (880,1180,"MCP prism · lit = tool call",(1007,1275)),(700,1440,"one point of light = one real message",(905,1345)),
              (880,20,"thinking glyphs · placement A (above)",(760,60)),(1700,520,"placement B (sternum)",(2010,455)),
              (1230,1510,"empty seat lip = Martin's input arriving",(1404,1485)),(60,1250,"waveguides follow the existing cable routes",(285,1331))]
        for x,y,t,(ax,ay) in labs:
            bb=d.multiline_textbbox((x,y),t,font=f); d.rectangle([bb[0]-8,bb[1]-6,bb[2]+8,bb[3]+6],fill=(0,0,0,150))
            d.multiline_text((x,y),t,font=f,fill=(235,225,205,255))
            sx=min(max(ax,bb[0]),bb[2]); sy=bb[1]-6 if ay<bb[1] else bb[3]+6
            d.line([(sx,sy),(ax,ay)],fill=(235,225,205,150),width=1)
    return img
import os; os.makedirs('../out',exist_ok=True)
Image.fromarray((grade(Image.open('source.jpg').convert('RGB'))*255).astype(np.uint8)).save('../out/00_graded_base_only.jpg',quality=93)
render(False).save('../out/01_quiet.jpg',quality=93)
render(True).save('../out/02_active.jpg',quality=93)
render(True,True).save('../out/03_active_annotated.jpg',quality=93)
print('done')
