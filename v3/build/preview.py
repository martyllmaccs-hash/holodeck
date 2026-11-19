# Offline composite of every layer at full level (layout check only; QML does the real render).
import json, re, sys
from PIL import Image
sc = json.loads(re.search(r'var scene = (.*);\n', open('holo-v3/Scene.js').read()).group(1))
A = 'holo-v3/assets/'
im = Image.open(A + 'base.jpg').convert('RGBA')
skip = set(sys.argv[1:])
for name, b in sc['layers'].items():
    if any(name.startswith(s) for s in skip): continue
    im.alpha_composite(Image.open(A + name + '.png'), (b['x'], b['y']))
tw = Image.open(A + 'twinkle.png')
for t in sc['twinkles']:
    im.alpha_composite(tw, (int(t['x'] - 10), int(t['y'] - 10)))
im.convert('RGB').save('/opt/data/cache/scratch/hv3/preview_all.jpg', quality=90)
