# Holodeck v3 asset builder: turns the approved mockup (work/paint.py) into separate
# glow layers + geometry for the live QML scene. Lana and Mila stay static (baked into
# the graded room photo); every overlay element becomes its own cropped RGBA layer so
# QML can drive it from fleet state.
# Run with: work/venv/bin/python build/build_assets.py   (needs numpy, cv2, scipy, PIL)
import os, json, math
import numpy as np, cv2
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.dirname(HERE)
OUT = os.path.join(HERE, 'holo-v3', 'assets')
os.makedirs(OUT, exist_ok=True)

# Reuse the mockup's drawing code verbatim (everything above its render calls).
src = open(os.path.join(PROJ, 'work', 'paint.py')).read().split('import os; os.makedirs')[0]
os.chdir(os.path.join(PROJ, 'work'))
exec(src)  # defines W,H,WARM,COOL,IVORY,WHITE,grade,Layer,bez,smooth,draw_net,LC,ARC_L,ARC_R,HC,HR

DW, DH = 1920, 1080
S = DW / W
ROSE = (1.0, 0.66, 0.62)
manifest = {'layers': {}, 'nets': [], 'twinkles': [], 'runs': {}, 'prisms': [], 'glyphs': {}}

def to_rgba(g):
    """Additive glow (black bg) -> straight RGBA that composites ~like a screen blend."""
    g = np.clip(g, 0, 1)
    a = g.max(2)
    rgb = np.where(a[..., None] > 1e-4, g / np.maximum(a[..., None], 1e-4), 0)
    return np.dstack([rgb, a])

def save_layer(name, g):
    rgba = to_rgba(g)
    small = cv2.resize(rgba.astype(np.float32), (DW, DH), interpolation=cv2.INTER_AREA)
    a = small[..., 3]
    ys, xs = np.where(a > 2 / 255)
    if not len(xs):
        print('empty layer', name); return
    x0, x1, y0, y1 = max(0, xs.min() - 2), min(DW, xs.max() + 3), max(0, ys.min() - 2), min(DH, ys.max() + 3)
    crop = (np.clip(small[y0:y1, x0:x1], 0, 1) * 255).astype(np.uint8)
    Image.fromarray(crop, 'RGBA').save(os.path.join(OUT, name + '.png'), optimize=True)
    manifest['layers'][name] = {'x': int(x0), 'y': int(y0), 'w': int(x1 - x0), 'h': int(y1 - y0)}

def d(p): return [round(p[0] * S, 1), round(p[1] * S, 1)]

# ---------------------------------------------------------------- base
base = grade(Image.open('source.jpg').convert('RGB'))
Image.fromarray((base * 255).astype(np.uint8)).resize((DW, DH), Image.LANCZOS).save(os.path.join(OUT, 'base.jpg'), quality=92)

# floor mask: substrate passes behind both women's legs and the chair base
lm = np.ones((H, W), np.float32)
for x0, x1 in ((655, 845), (1985, 2185)): cv2.rectangle(lm, (x0, 1120), (x1, 1560), 0, -1)
cv2.rectangle(lm, (1230, 1100), (1575, 1500), 0.0, -1)
lm = cv2.GaussianBlur(lm, (0, 0), 10)
manifest['masks'] = [[655 * S, 1120 * S, 845 * S, 1560 * S], [1985 * S, 1120 * S, 2185 * S, 1560 * S], [1230 * S, 1100 * S, 1575 * S, 1500 * S]]

# ---------------------------------------------------------------- floor substrate (one layer per side)
runs = {}
PR = {'L': [(540, 1319), (1007, 1290), (337, 1345)], 'R': [(1791, 1290), (2249, 1327), (2475, 1360)]}
for side, col in (('L', WARM), ('R', COOL)):
    F = Layer()
    for k, c in enumerate(LC[side]):
        s = smooth(c); F.line(s, col, 0.55 if k == 0 else 0.36, 2 if k == 0 else 1)
        if k == 0: runs[side] = s
        for j in range(12, len(s) - 6, 17 + 5 * k):
            F.dot(*s[j], 1.7, col, 0.5)
            if j % 2 == 0:
                dv = s[j + 1] - s[j]; n = np.array([-dv[1], dv[0]]) / (np.linalg.norm(dv) + 1e-6)
                e = s[j] + n * (14 + 6 * k) * (1 if k != 1 else -1) + dv * 2; F.line([s[j], e], col, 0.4, 1); F.dot(*e, 1.6, col, 0.6)
    arc = smooth(ARC_L if side == 'L' else ARC_R, 80); F.line(arc, IVORY, 0.26, 1)
    for (x, y) in PR[side]:   # resting prisms
        dd = np.array([(0, -17), (11, 0), (0, 9), (-11, 0), (0, -17)]) + (x, y - 6)
        F.line(dd, IVORY, 0.62, 1); F.line([dd[0], dd[2]], IVORY, 0.22, 1)
    save_layer('floor_' + side, F.glow(lm))
    manifest['runs'][side] = [d(p) for p in runs[side]]

# lit prisms (tool call)
for side in 'LR':
    for i, (x, y) in enumerate(PR[side]):
        P = Layer()
        dd = np.array([(0, -17), (11, 0), (0, 9), (-11, 0), (0, -17)]) + (x, y - 6)
        P.line(dd, IVORY, 1.0, 2); P.line([dd[0], dd[2]], IVORY, 0.5, 1)
        for ang, cc in ((-62, (1, 0.55, 0.4)), (-90, (1, 0.95, 0.7)), (-118, (0.5, 0.85, 1))):
            a = math.radians(ang); P.line([(x, y - 24), (x + 30 * math.cos(a), y - 24 + 30 * math.sin(a))], cc, 0.5, 1)
        name = 'prism_%s%d' % (side, i); save_layer(name, P.glow())
        manifest['prisms'].append({'name': name, 'side': side, 'slot': i})

# ---------------------------------------------------------------- Hindsight memory drum
rng = np.random.default_rng(7); A = Layer()
for deg in np.arange(142, 400, 1.6):
    a = math.radians(deg); v = rng.random(); r0 = HR + 12; r1 = r0 + 6 + 16 * v ** 2
    A.line([(HC[0] + r0 * math.cos(a), HC[1] + r0 * math.sin(a)), (HC[0] + r1 * math.cos(a), HC[1] + r1 * math.sin(a))], IVORY, 0.2 + 0.5 * v, 1)
A.line([(HC[0] + (HR + 8) * math.cos(math.radians(t)), HC[1] + (HR + 8) * math.sin(math.radians(t))) for t in np.arange(142, 400, 1)], IVORY, 0.3, 1)
save_layer('drum', A.glow())
A = Layer()
A.line([(HC[0] + (HR + 8) * math.cos(math.radians(t)), HC[1] + (HR + 8) * math.sin(math.radians(t))) for t in np.arange(205, 236, 1)], IVORY, 1.0, 3)
for deg in np.arange(205, 236, 1.6):
    a = math.radians(deg); A.line([(HC[0] + (HR + 12) * math.cos(a), HC[1] + (HR + 12) * math.sin(a)), (HC[0] + (HR + 34) * math.cos(a), HC[1] + (HR + 34) * math.sin(a))], IVORY, 0.95, 1)
save_layer('drum_write', A.glow())

# seat lip (a turn starting = Martin's input arriving)
A = Layer(); A.line([(1262, 1481), (1546, 1481)], IVORY, 1.0, 2); save_layer('seat_lip', A.glow())

# ---------------------------------------------------------------- nets
def nearest_idx(run, p):
    return int(np.argmin(((run - np.array(p)) ** 2).sum(1)))

def add_net(nid, machine, kind, cx, cy, sc, col, seed, rot=0, eyes=False, drop=None, extra=None, label=None, tw_frac=0.3, colname='warm'):
    """drop: list of bezier control-quads from the net down to its floor run (for tendrils + pulse routes)."""
    L = Layer()
    P, ends = draw_net(L, kind, cx, cy, sc, col, 1.0, seed, rot, lit=0.0, eyes=eyes)
    side = 'L' if machine == 'vps' else 'R'
    route = [(cx, cy)]
    for q in (drop or []):
        pts = bez(*q, 80); L.line(pts, col, 0.5 if kind in ('lana', 'mila') else 0.36, 1); route += [tuple(p) for p in pts]
    for q in (extra or []):
        L.line(bez(*q, 80), col, 0.3, 1)
    name = 'net_%s_%s' % (machine, nid)
    save_layer(name, L.glow())
    entry = {'id': nid, 'machine': machine, 'layer': name, 'cx': cx * S, 'cy': cy * S, 'sc': sc * S, 'color': colname, 'label': label or nid.upper()}
    if drop:
        run = runs[side]; idx = nearest_idx(run, route[-1])
        entry.update({'side': side, 'runIdx': idx, 'drop': [d(p) for p in route[::4]] + [d(run[idx])]})
    manifest['nets'].append(entry)
    rng2 = np.random.default_rng(seed + 100)
    k = max(2, int(round(len(P) * tw_frac)))
    for i in rng2.choice(len(P), k, replace=False):
        manifest['twinkles'].append({'net': name, 'machine': machine, 'id': nid, 'x': round(P[i][0] * S, 1), 'y': round(P[i][1] * S, 1),
                                     'ph': round(float(rng2.uniform(0, 6.283)), 3), 'sp': round(float(rng2.uniform(0.9, 2.6)), 3),
                                     'big': bool(kind == 'lana' and i < 13)})

# Lana (VPS orchestrator) and Mila (P1 orchestrator): as in the mockup
add_net('default', 'vps', 'lana', 395, 205, 150, WARM, 11, label='LANA', tw_frac=0.42,
        drop=[((330, 330), (380, 520), (445, 700), (442, 1100)), ((442, 1100), (442, 1220), (470, 1300), (540, 1332))],
        extra=[((560, 150), (820, 40), (1150, 30), (1396, 118))])
add_net('p1-mila', 'p1', 'mila', 2420, 210, 150, COOL, 5, label='MILA', colname='cool', tw_frac=0.3,
        drop=[((2485, 330), (2440, 520), (2362, 700), (2362, 1100)), ((2362, 1100), (2362, 1220), (2330, 1300), (2260, 1335))],
        extra=[((2330, 120), (2050, 30), (1680, 30), (1416, 118))])

# Lana's specialists down the left wall (one net per real VPS profile)
def staff_drop(x, y, sc, side):
    fx = x + (70 if side == 'L' else -70)
    fy = 1331 if side == 'L' else 1336
    return [((x, y + sc * 0.9), (x, y + 120), (fx, fy - 140), (fx, fy))]

LEFT = [('researcher', 'fan', 200, 470, 42), ('analyst', 'ring', 395, 565, 32), ('architect', 'helix', 150, 665, 44),
        ('auditor', 'fan', 360, 770, 38), ('librarian', 'ring', 165, 885, 34), ('news', 'helix', 390, 975, 40),
        ('ride-test', 'fan', 175, 1095, 32)]
for i, (nid, kind, x, y, sc) in enumerate(LEFT):
    add_net(nid, 'vps', kind, x, y, sc, WARM, 21 + i, rot=0.15 if kind == 'helix' else 0, drop=staff_drop(x, y, sc, 'L'))
# playroom floats free and unlinked beside Lana's hip, rose gold
add_net('playroom', 'vps', 'ring', 960, 625, 28, ROSE, 41, colname='rose', label='PLAYROOM')
# spare slots for VPS profiles that appear later
for i, (x, y) in enumerate([(60, 380), (60, 1010)]):
    add_net('__spare_vps_%d' % i, 'vps', 'ring', x, y, 26, WARM, 51 + i, drop=staff_drop(x, y, 26, 'L'), label='')

# Mila's staff down the right wall; staff4 is the derpy one
RIGHT = [('staff1', 'ring', 2480, 495, 40, 0.3), ('staff2', 'fan', 2650, 700, 40, 0), ('staff3', 'helix', 2470, 905, 44, -0.15)]
for i, (nid, kind, x, y, sc, rot) in enumerate(RIGHT):
    add_net(nid, 'p1', kind, x, y, sc, COOL, 61 + i, rot=rot, colname='cool', drop=staff_drop(x, y, sc, 'R'))
add_net('staff4', 'p1', 'derpy', 2575, 1215, 50, COOL, 2, rot=math.radians(-13), eyes=True, colname='cool',
        drop=[((2650, 1180), (2620, 1290), (2560, 1330), (2480, 1350))], tw_frac=0.6)
for i, (x, y) in enumerate([(2760, 420), (2760, 1000)]):
    add_net('__spare_p1_%d' % i, 'p1', 'ring', x, y, 26, COOL, 71 + i, colname='cool', drop=staff_drop(x, y, 26, 'R'), label='')

# thinking-glyph threads (placement A, above each sister)
A = Layer(); A.line(bez((560, 235), (600, 200), (610, 150), (640, 112), 60), WARM, 0.5, 1); save_layer('glyph_thread_L', A.glow())
A = Layer(); A.line(bez((2256, 235), (2216, 200), (2206, 150), (2176, 112), 60), COOL, 0.5, 1); save_layer('glyph_thread_R', A.glow())
manifest['glyphs'] = {'L': d((728, 94)), 'R': d((2088, 94))}
manifest['hub'] = {'L': d(runs['L'][0]), 'R': d(runs['R'][0])}
manifest['prismSlots'] = {s: [d(p) for p in PR[s]] for s in 'LR'}

# ---------------------------------------------------------------- sprites
def sprite(name, size, core, col, glow=0.55):
    yy, xx = np.mgrid[0:size, 0:size].astype(np.float32); c = (size - 1) / 2
    r = np.hypot(xx - c, yy - c)
    a = np.clip(core + 0.5 - r, 0, 1) + glow * np.exp(-(r / (size * 0.18)) ** 2) + 0.35 * glow * np.exp(-(r / (size * 0.34)) ** 2)
    g = np.dstack([a * col[0], a * col[1], a * col[2]])
    Image.fromarray((np.clip(to_rgba(g), 0, 1) * 255).astype(np.uint8), 'RGBA').save(os.path.join(OUT, name + '.png'))
sprite('spark', 48, 3.6, (1, 1, 1), 0.9)        # one point of light = one real message
sprite('twinkle', 20, 1.6, (1, 1, 1), 0.7)
sprite('twinkle_big', 26, 2.1, (1, 1, 1), 0.75)

# ---------------------------------------------------------------- scene file for QML
js = '.pragma library\n// Generated by build/build_assets.py. Do not edit by hand.\nvar scene = ' + json.dumps(manifest, separators=(',', ':')) + ';\n'
open(os.path.join(HERE, 'holo-v3', 'Scene.js'), 'w').write(js)
print('layers', len(manifest['layers']), 'nets', len(manifest['nets']), 'twinkles', len(manifest['twinkles']))
