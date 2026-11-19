# Holodeck v3 figure states: dormant still + dormant->attention clip (and its reverse),
# graded and cropped exactly like build_assets.py makes base.jpg, so they sit on the
# live stage with no seam. Attention = base.jpg itself (the original render pose).
#   usage: build_figures.py lana|mila [...]
# Output: holo-v3/assets/fig_<n>_dormant.jpg, fig_<n>_rise.mp4, fig_<n>_fall.mp4,
#         and a FIG dict appended to stdout for Scene.js (stage box per sister).
import sys, os, subprocess, json, shutil
import numpy as np, cv2
from PIL import Image, ImageFilter, ImageChops

P = '/opt/data/projects/Holodeck v3/'
OUT = P + 'build/holo-v3/assets/'
W, H, DW, DH = 2816, 1584, 1920, 1080
S = DW / W
X0 = {'lana': 231, 'mila': 1666}
CW = 900
# Wan ended Lana's rise ~6-11 source px left of the real pose (upper body, feet fine) and then
# snapped right in its last frames (Martin saw it, flow measured it). From SETTLE[n] on, warp each
# frame toward the original with heavily smoothed optical flow, weight easing 0 -> 1 by the end,
# so the correction hides inside the rise instead of showing as a slide at the hand-off.
SETTLE = {'lana': 80}
# Wan also drifts Lana's colour: frame 1 ~3.5 levels darker than the dormant still, then she warms
# up to +6 R/+5 B mid-rise, and Wan's last 2 frames snap her back (Martin: "your colours change").
# COLOUR grades each frame's figure so her body-core mean glides smoothly dormant -> original.
COLOUR = {'lana'}

src = np.asarray(Image.open(P + 'work/source.jpg').convert('RGB')).astype(np.float32) / 255
yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
VIG = (1 - 0.42 * np.clip(((xx - W / 2) / (W * 0.62)) ** 2 + ((yy - H * 0.46) / (H * 0.72)) ** 2, 0, 1) ** 1.4)[..., None]

def grade_px(a, vig):  # work/paint.py grade(), per-pixel part, with the vignette slice passed in
    a = a ** 1.06
    a = a + 0.42 * (a * a * (3 - 2 * a) - a)
    lum = a.mean(2, keepdims=True)
    a = lum + (a - lum) * 1.22
    sh = np.clip(1 - lum * 3, 0, 1); hi = np.clip((lum - 0.55) * 2.2, 0, 1)
    a = a + sh * np.array([-0.012, 0.004, 0.02]) + hi * np.array([0.03, 0.012, -0.02])
    return np.clip(a * vig, 0, 1)

BASE = (grade_px(src, VIG) * 255).astype(np.uint8)          # == build_assets base before resize

def box(n):
    x0 = int(np.floor(X0[n] * S)) - 1; x1 = int(np.ceil((X0[n] + CW) * S)) + 1
    if (x1 - x0) % 2: x1 += 1
    return x0, x1

def stage_crop(n, crop_rgb):
    """crop_rgb: 900x1584 uint8 (ungraded, source space) -> graded stage-space crop."""
    x = X0[n]
    g = BASE.copy()
    g[:, x:x + CW] = (grade_px(crop_rgb.astype(np.float32) / 255, VIG[:, x:x + CW]) * 255).astype(np.uint8)
    full = Image.fromarray(g).resize((DW, DH), Image.LANCZOS)
    x0, x1 = box(n)
    return full.crop((x0, 0, x1, DH))

def motion_mask(n):
    p = P + f'crop/{n}_motion_mask.png'
    if not os.path.exists(p):
        a = Image.open(P + f'crop/{n}_dormant_cut.png').getchannel('A').point(lambda v: 255 if v > 10 else 0)
        old = Image.open(P + f'crop/{n}_oldfig_mask.png').convert('L')
        m = ImageChops.lighter(a, old).filter(ImageFilter.MaxFilter(41)).filter(ImageFilter.GaussianBlur(18))
        m.save(p)
    return Image.open(p).convert('L')

def settle(n, frames_rgb, og, mask):
    """frames_rgb: list of HxWx3 uint8 (source crop space). Returns corrected list."""
    s0 = SETTLE.get(n)
    if s0 is None: return frames_rgb
    nf = len(frames_rgb); h, w = og.shape[:2]
    og_s = cv2.resize(cv2.cvtColor(og, cv2.COLOR_RGB2GRAY), (w // 2, h // 2), interpolation=cv2.INTER_AREA)
    m = (np.asarray(mask).astype(np.float32) / 255)[..., None]
    flows = {}
    for i in range(s0 - 4, nf):
        fr = cv2.resize(cv2.cvtColor(frames_rgb[i], cv2.COLOR_RGB2GRAY), (w // 2, h // 2), interpolation=cv2.INTER_AREA)
        f = cv2.calcOpticalFlowFarneback(og_s, fr, None, 0.5, 5, 31, 5, 7, 1.5, 0)   # og pixel -> where it is in frame
        f = cv2.GaussianBlur(f, (0, 0), 12)                                            # low-frequency shift only
        flows[i] = cv2.resize(f, (w, h), interpolation=cv2.INTER_LINEAR) * 2
    gy, gx = np.mgrid[0:h, 0:w].astype(np.float32)
    out = list(frames_rgb)
    for i in range(s0, nf):
        f = np.mean([flows[j] for j in range(max(s0 - 4, i - 4), min(nf, i + 5))], axis=0) * m   # temporal smoothing
        t = (i - s0) / (nf - 1 - s0); wgt = t * t * (3 - 2 * t)
        out[i] = cv2.remap(frames_rgb[i], gx + wgt * f[..., 0], gy + wgt * f[..., 1], cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
    return out

def colour_settle(n, frames_rgb, og, dormant):
    if n not in COLOUR: return frames_rgb
    old = np.asarray(Image.open(P + f'crop/{n}_oldfig_mask.png').convert('L')) > 128
    cut = np.asarray(Image.open(P + f'crop/{n}_dormant_cut.png').getchannel('A')) > 10
    core = cv2.erode(old.astype(np.uint8), np.ones((31, 31))) > 0             # her body in every frame
    fig = cv2.GaussianBlur(cv2.dilate((old | cut).astype(np.uint8) * 255, np.ones((31, 31))), (0, 0), 12).astype(np.float32)[..., None] / 255
    nf = len(frames_rgb)
    c0 = dormant[core].astype(np.float64).mean(0); c1 = og[core].astype(np.float64).mean(0)
    raw = np.array([f[core].astype(np.float64).mean(0) for f in frames_rgb])
    t = np.linspace(0, 1, nf)[:, None]; tgt = c0 + (c1 - c0) * (t * t * (3 - 2 * t))
    g = tgt / raw
    gp = np.pad(g, ((2, 2), (0, 0)), mode='edge')                            # light smoothing only: Wan's own drop at
    gs = np.array([gp[i:i + 5].mean(0) for i in range(nf)])                   # the end must be cancelled frame-exact
    gs[-3:] = g[-3:]                                                          # land exactly: last frames are near-original anyway
    out = []
    for i, f in enumerate(frames_rgb):
        x = f.astype(np.float32)
        out.append(np.clip(x * (1 + fig * (gs[i].astype(np.float32) - 1)), 0, 255).astype(np.uint8))
    return out

def build(n):
    og = Image.open(P + f'crop/{n}_og_900.png').convert('RGB')
    dormant = Image.open(P + f'crop/{n}_dormant_final.png').convert('RGB')
    stage_crop(n, np.asarray(dormant)).save(OUT + f'fig_{n}_dormant.jpg', quality=92)

    raw = P + f'gen/transition_{n}_dormant_to_attention_wan3.mp4'
    tmp = f'/opt/data/cache/scratch/fig_{n}'
    shutil.rmtree(tmp, ignore_errors=True); os.makedirs(tmp + '/in'); os.makedirs(tmp + '/out')
    subprocess.run(['ffmpeg', '-v', 'error', '-i', raw, '-vf', f'scale={CW}:{H}:flags=lanczos', tmp + '/in/%03d.png'], check=True)
    frames = sorted(os.listdir(tmp + '/in'))
    mask = motion_mask(n)
    lockedv = [np.asarray(Image.composite(Image.open(f'{tmp}/in/{f}').convert('RGB'), og, mask)) for f in frames]
    lockedv = settle(n, lockedv, np.asarray(og), mask)
    lockedv = colour_settle(n, lockedv, np.asarray(og), np.asarray(dormant))
    nf = len(frames); fade = 8   # last frames ease onto the exact original pixels: no pop at hand-off to base.jpg
    stats = []
    for i, f in enumerate(frames):
        locked = Image.fromarray(lockedv[i])                         # room outside the figure = original
        if i == 0: locked = dormant                                  # first frame = the dormant still exactly
        k = (i - (nf - 1 - fade)) / fade
        if k > 0: locked = Image.blend(locked, og, min(1, k))
        sc = stage_crop(n, np.asarray(locked))
        sc.save(f'{tmp}/out/{i:03d}.png')
        if i in (0, nf - 1): stats.append(sc)
    enc = ['-c:v', 'libx264', '-crf', '16', '-preset', 'slow', '-pix_fmt', 'yuv420p', '-g', '30', '-movflags', '+faststart', '-an']
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-framerate', '30', '-i', tmp + '/out/%03d.png'] + enc + [OUT + f'fig_{n}_rise.mp4'], check=True)
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-framerate', '30', '-i', tmp + '/out/%03d.png', '-vf', 'reverse'] + enc + [OUT + f'fig_{n}_fall.mp4'], check=True)
    # seam checks vs base.jpg (stage space)
    base = Image.open(OUT + 'base.jpg').convert('RGB'); x0, x1 = box(n); bc = np.asarray(base.crop((x0, 0, x1, DH))).astype(int)
    dor = np.asarray(Image.open(OUT + f'fig_{n}_dormant.jpg')).astype(int)
    last = np.asarray(stats[1]).astype(int)
    m = np.asarray(mask.resize((x1 - x0, DH))) < 3   # outside motion mask (approx, stage space)
    rep = {'box': [x0, 0, x1 - x0, DH], 'frames': nf,
           'dormant_vs_base_outside_mean': round(float(np.abs(dor - bc)[m].mean()), 2),
           'last_vs_base_mean': round(float(np.abs(last - bc).mean()), 2),
           'last_vs_base_max': int(np.abs(last - bc).max())}
    shutil.rmtree(tmp, ignore_errors=True)
    return rep

if __name__ == '__main__':
    print(json.dumps({n: build(n) for n in sys.argv[1:]}))
