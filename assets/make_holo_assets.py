#!/usr/bin/env python3
"""
make_holo_assets.py -- procedural asset set for the holographic-blue orchestration
display (quickshell/holo).

Everything is generated from one integer seed.  Same seed -> byte-identical PNGs.

    python3 make_holo_assets.py                 # writes into ./  (the assets dir)
    python3 make_holo_assets.py --seed 20260923 --out /path/to/assets
    python3 make_holo_assets.py --report        # alpha / channel report per file

Requires only Pillow + numpy.

Outputs (all RGBA):
    galaxy.png      1920x1080  deep-space backdrop: nebula + milky-way band + vignette
    stars.png       1920x1080  independent star layer (twinkle over the nebula)
    grid.png        1920x1080  faint cyan technical grid, 48 px cells, radial falloff
    glow-node.png    512x512   radial node glow, cyan-white core -> transparent
    glow-pulse.png   256x256   tighter/hotter pulse sprite for a travelling dot
    scanlines.png   1920x1080  CRT scanline overlay, 1 px every 3 px, very low alpha
    cone.png        1920x1080  projector cone rising from the bottom centre edge

Palette is fixed by the build contract's "Visual canon - holographic blue":
deep navy/black space, cyan grid and glow, faint violet in the nebula.
"""

from __future__ import annotations

import argparse
import os
import sys

import numpy as np
from PIL import Image

W, H = 1920, 1080
DEFAULT_SEED = 20260923

# --------------------------------------------------------------------------- #
# palette
# --------------------------------------------------------------------------- #
VOID      = np.array([2, 5, 16], np.float32)      # deep space
NAVY      = np.array([8, 32, 78], np.float32)     # nebula body
CYAN      = np.array([0, 214, 255], np.float32)   # nebula highlight / UI accent
CYAN_PALE = np.array([168, 242, 255], np.float32)
VIOLET    = np.array([124, 96, 255], np.float32)
STAR_WHITE = np.array([236, 248, 255], np.float32)

# per-asset sub-seeds: fixed tags keep every asset stable if another one changes
TAGS = {
    "galaxy": 11, "stars": 22, "grid": 33, "glow_node": 44,
    "glow_pulse": 55, "scanlines": 66, "cone": 77,
}


def rng_for(seed: int, tag: int) -> np.random.Generator:
    return np.random.default_rng([int(seed), int(tag)])


# --------------------------------------------------------------------------- #
# noise helpers
# --------------------------------------------------------------------------- #
def _grid_noise(shape, res, rng):
    """Smooth non-periodic noise: random grid, bicubic-upsampled to `shape`."""
    gh, gw = max(2, int(round(res[0]))), max(2, int(round(res[1])))
    g = rng.random((gh, gw), dtype=np.float32)
    im = Image.fromarray(g).resize((shape[1], shape[0]), Image.BICUBIC)
    return np.clip(np.asarray(im, dtype=np.float32), 0.0, 1.0)


def fbm(shape, rng, octaves=5, res=(4, 7), gain=0.5, lac=2.0):
    """Fractal brownian motion, normalised to 0..1."""
    out = np.zeros(shape, np.float32)
    amp, norm = 1.0, 0.0
    gw, gh = float(res[1]), float(res[0])
    for _ in range(octaves):
        out += amp * _grid_noise(shape, (gh, gw), rng)
        norm += amp
        amp *= gain
        gw *= lac
        gh *= lac
    return out / norm


def ridged(n):
    """Ridged transform -- turns fbm into filaments/veins."""
    return 1.0 - np.abs(2.0 * n - 1.0)


def smoothstep(t):
    t = np.clip(t, 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def sample_bilinear(field, X, Y):
    """Bilinear lookup of `field` at float coords (used for domain warping)."""
    x0 = np.clip(np.floor(X).astype(np.int32), 0, field.shape[1] - 2)
    y0 = np.clip(np.floor(Y).astype(np.int32), 0, field.shape[0] - 2)
    fx = (X - x0).astype(np.float32)
    fy = (Y - y0).astype(np.float32)
    a = field[y0, x0] * (1 - fx) * (1 - fy)
    b = field[y0, x0 + 1] * fx * (1 - fy)
    c = field[y0 + 1, x0] * (1 - fx) * fy
    d = field[y0 + 1, x0 + 1] * fx * fy
    return a + b + c + d


def coords():
    yy, xx = np.mgrid[0:H, 0:W]
    return xx.astype(np.float32), yy.astype(np.float32)


def band_field(rng, angle_deg=-32.0, sigma=170.0, warp_v=300.0, warp_u=180.0,
               cx=W * 0.5, cy=H * 0.50):
    """The galaxy band: a warped gaussian ridge running on a diagonal."""
    xx, yy = coords()
    ang = np.deg2rad(angle_deg)
    ax, ay = np.cos(ang), np.sin(ang)
    px, py = -np.sin(ang), np.cos(ang)
    u = (xx - cx) * ax + (yy - cy) * ay
    v = (xx - cx) * px + (yy - cy) * py
    # domain warp: the band snakes instead of reading as a straight stripe
    v = v - (fbm((H, W), rng, 4, (5, 8)) - 0.5) * warp_v
    u = u - (fbm((H, W), rng, 4, (5, 8)) - 0.5) * warp_u
    return np.exp(-(v / sigma) ** 2), u, v


def splat(lum, col, cx, cy, sigma, amp, tint, halo=0.0, halo_amp=0.16):
    """Additive gaussian point light. `halo` adds a wide soft bloom."""
    R = int(np.ceil(max(sigma, halo) * 3.2)) + 2
    x0, x1 = max(0, int(cx) - R), min(W, int(cx) + R + 1)
    y0, y1 = max(0, int(cy) - R), min(H, int(cy) + R + 1)
    if x0 >= x1 or y0 >= y1:
        return
    yy, xx = np.mgrid[y0:y1, x0:x1]
    d2 = (xx - cx) ** 2 + (yy - cy) ** 2
    g = np.exp(-d2 / (2.0 * sigma * sigma)).astype(np.float32) * amp
    if halo > 0.0:
        g += (np.exp(-d2 / (2.0 * halo * halo)).astype(np.float32) * amp * halo_amp)
    lum[y0:y1, x0:x1] += g
    col[y0:y1, x0:x1] += g[:, :, None] * tint[None, None, :]


def flare(lum, col, cx, cy, length, width, amp, tint):
    """Subtle 4-point diffraction flare (a plus of two thin gaussians)."""
    R = int(length * 1.6) + 2
    x0, x1 = max(0, int(cx) - R), min(W, int(cx) + R + 1)
    y0, y1 = max(0, int(cy) - R), min(H, int(cy) + R + 1)
    if x0 >= x1 or y0 >= y1:
        return
    yy, xx = np.mgrid[y0:y1, x0:x1]
    dx = (xx - cx).astype(np.float32)
    dy = (yy - cy).astype(np.float32)
    horiz = np.exp(-(dx / length) ** 2) * np.exp(-(dy / width) ** 2)
    vert = np.exp(-(dy / length) ** 2) * np.exp(-(dx / width) ** 2)
    g = (horiz + vert).astype(np.float32) * amp
    lum[y0:y1, x0:x1] += g
    col[y0:y1, x0:x1] += g[:, :, None] * tint[None, None, :]


def sample_weighted(rng, n, weight):
    """`n` positions whose density follows `weight` (0..1), by rejection."""
    xs, ys = [], []
    got = 0
    while got < n:
        k = max(128, (n - got) * 2)
        cx = rng.random(k, dtype=np.float32) * (W - 1)
        cy = rng.random(k, dtype=np.float32) * (H - 1)
        p = 0.20 + 0.80 * weight[cy.astype(np.int32), cx.astype(np.int32)]
        keep = rng.random(k, dtype=np.float32) < p
        if keep.any():
            xs.append(cx[keep])
            ys.append(cy[keep])
            got += int(keep.sum())
    return np.concatenate(xs)[:n], np.concatenate(ys)[:n]


def to_u8(arr):
    return np.clip(np.rint(arr), 0, 255).astype(np.uint8)


def save(path, rgb, alpha):
    rgba = np.dstack([to_u8(rgb), to_u8(alpha)]).astype(np.uint8)
    Image.fromarray(rgba, "RGBA").save(path)
    return rgba


# --------------------------------------------------------------------------- #
# 1. galaxy.png
# --------------------------------------------------------------------------- #
def make_galaxy(rng):
    xx, yy = coords()
    band, u, v = band_field(rng, angle_deg=-32.0, sigma=170.0)
    halo = np.exp(-(v / 470.0) ** 2) * np.exp(-(u / 1000.0) ** 2)
    core = np.exp(-(u / 700.0) ** 2)

    # filaments (domain-warped ridged fbm) -> the nebula reads as gas, not grain
    warp_x = fbm((H, W), rng, 4, (6, 10))
    warp_y = fbm((H, W), rng, 4, (6, 10))
    fil_raw = fbm((H, W), rng, 5, (9, 15))
    fil = sample_bilinear(fil_raw, xx + (warp_x - 0.5) * 190.0,
                          yy + (warp_y - 0.5) * 190.0)
    fil = ridged(fil) ** 1.7

    cloud = fbm((H, W), rng, 5, (4, 7))
    dust = fbm((H, W), rng, 4, (12, 20))
    dust_mask = np.clip((dust - 0.52) * 3.0, 0.0, 1.0) * band

    neb = band * (0.28 + 1.05 * fil) * (0.38 + 0.82 * cloud)
    neb = neb * (0.52 + 0.68 * core)
    neb += 0.34 * halo * (0.25 + 0.75 * cloud)
    neb *= (1.0 - 0.62 * dust_mask)
    neb = np.clip(neb, 0.0, None)
    neb /= max(float(np.percentile(neb, 99.6)), 1e-6)
    neb = np.clip(neb, 0.0, 1.0)

    # colour ramp: void -> navy -> cyan, violet folded in around the halo
    t = neb
    lo = np.clip(t * 2.6, 0.0, 1.0)[:, :, None]
    hi = np.clip((t - 0.26) * 1.9, 0.0, 1.0)[:, :, None]
    col = VOID[None, None, :] + (NAVY - VOID)[None, None, :] * lo \
        + (CYAN - NAVY)[None, None, :] * hi
    vio_field = np.clip(fbm((H, W), rng, 4, (6, 11)) * 1.6 - 0.55, 0.0, 1.0)
    w = np.clip(vio_field * halo * 0.75, 0.0, 1.0)[:, :, None]
    col = col * (1.0 - w) + VIOLET[None, None, :] * w

    col *= 0.90                       # headroom so stars/haze can sit on top

    # unresolved star haze -- the milky-way grain inside the band (0..255 units!)
    haze = (fbm((H, W), rng, 3, (300, 520)) ** 2.2) * band * 1.0
    haze += (fbm((H, W), rng, 2, (620, 980)) ** 2.6) * band * 0.45
    col += haze[:, :, None] * np.array([19.0, 40.0, 52.0], np.float32)[None, None, :]

    # resolved stars, strongly biased into the band
    lum = np.zeros((H, W), np.float32)
    sc = np.zeros((H, W, 3), np.float32)
    n = 1800
    sx, sy = sample_weighted(rng, n, band)
    mags = rng.random(n, dtype=np.float32) ** 2.6
    tint = np.empty((n, 3), np.float32)
    pick = rng.random(n, dtype=np.float32)
    tint[:] = STAR_WHITE
    tint[pick < 0.22] = CYAN_PALE
    tint[(pick >= 0.22) & (pick < 0.30)] = np.array([214, 208, 255], np.float32)
    for i in range(n):
        m = float(mags[i])
        if m < 0.06:                       # faint dust -- skip most of them
            if rng.random() < 0.55:
                continue
        splat(lum, sc, float(sx[i]), float(sy[i]),
              sigma=0.40 + 1.35 * m, amp=0.16 + 0.90 * m,
              tint=tint[i], halo=1.5 + 3.0 * m if m > 0.55 else 0.0)
    col += np.clip(lum, 0.0, 2.0)[:, :, None] * np.array([205.0, 226.0, 240.0], np.float32)[None, None, :]

    # soft dark vignette at the edges
    rr = np.sqrt(((xx - W / 2) / (W * 0.60)) ** 2 + ((yy - H / 2) / (H * 0.60)) ** 2)
    vig = np.clip(1.0 - 0.74 * rr ** 2.3, 0.05, 1.0)
    col *= vig[:, :, None]

    # dither before quantising -> no visible banding in the dark gradients
    col += rng.normal(0.0, 0.42, col.shape).astype(np.float32)

    # alpha: opaque where the UI lives, softly fading over the outermost frame
    edge = np.minimum(np.minimum(xx, (W - 1) - xx), np.minimum(yy, (H - 1) - yy))
    m = smoothstep((edge - 26.0) / 96.0)
    alpha = 148.0 + 107.0 * m
    return col, alpha


# --------------------------------------------------------------------------- #
# 2. stars.png
# --------------------------------------------------------------------------- #
def make_stars(rng):
    lum = np.zeros((H, W), np.float32)
    col = np.zeros((H, W, 3), np.float32)
    band, _, _ = band_field(rng, angle_deg=-32.0, sigma=190.0,
                            warp_v=260.0, warp_u=150.0)

    n = 660
    sx, sy = sample_weighted(rng, n, band)
    mags = rng.random(n, dtype=np.float32) ** 2.7
    tint = np.empty((n, 3), np.float32)
    pick = rng.random(n, dtype=np.float32)
    tint[:] = STAR_WHITE
    tint[pick < 0.18] = CYAN_PALE
    tint[(pick >= 0.18) & (pick < 0.26)] = np.array([206, 200, 255], np.float32)

    order = np.argsort(mags)                     # dim first, bright on top
    flared = set(int(i) for i in order[-15:])
    for i in order:
        i = int(i)
        m = float(mags[i])
        splat(lum, col, float(sx[i]), float(sy[i]),
              sigma=0.38 + 0.85 * m, amp=0.22 + 0.85 * m, tint=tint[i],
              halo=2.0 + 4.5 * m if m > 0.55 else 0.0, halo_amp=0.24)
        if i in flared:
            flare(lum, col, float(sx[i]), float(sy[i]),
                  length=13.0 + 19.0 * m, width=0.70 + 0.35 * m,
                  amp=0.10 + 0.13 * m, tint=tint[i])

    # soft shoulder instead of a hard clip: bright cores stay gaussian, never
    # flatten into solid squares
    alpha = (1.0 - np.exp(-lum * 1.55)) ** 0.92
    rgb = np.clip(col / np.maximum(lum, 1e-5)[:, :, None], 0.0, 1.0) * 255.0
    hot = np.clip((lum - 0.75) * 1.2, 0.0, 1.0)[:, :, None]
    rgb = rgb * (1.0 - hot) + 255.0 * hot            # bright cores go white
    return rgb, alpha * 255.0


# --------------------------------------------------------------------------- #
# 3. grid.png
# --------------------------------------------------------------------------- #
def make_grid(rng):
    xx, yy = coords()
    xs = np.arange(W)
    ys = np.arange(H)
    minor, major = 34.0, 74.0
    xl = np.zeros(W, np.float32)
    xl[xs % 48 == 0] = minor
    xl[xs % 192 == 0] = major
    yl = np.zeros(H, np.float32)
    yl[ys % 48 == 0] = minor
    yl[ys % 192 == 0] = major
    a = np.zeros((H, W), np.float32)
    a = np.maximum(a, xl[None, :])
    a = np.maximum(a, yl[:, None])

    # soft radial falloff so it dissolves toward the edges
    r = np.sqrt(((xx - W / 2) / (W * 0.50)) ** 2 + ((yy - H / 2) / (H * 0.50)) ** 2)
    fall = np.clip(1.0 - r ** 2.6, 0.0, 1.0) ** 0.70
    a *= fall

    rgb = np.zeros((H, W, 3), np.float32)
    rgb[:] = np.array([96, 226, 255], np.float32)
    # major lines read slightly cooler/whiter
    xm = np.zeros(W, np.float32); xm[xs % 192 == 0] = 1.0
    ym = np.zeros(H, np.float32); ym[ys % 192 == 0] = 1.0
    major_m = np.maximum(xm[None, :], ym[:, None])[:, :, None]
    rgb = rgb * (1.0 - 0.35 * major_m) + np.array([196, 248, 255], np.float32)[None, None, :] * (0.35 * major_m)
    return rgb, a


# --------------------------------------------------------------------------- #
# 4/5. glow sprites
# --------------------------------------------------------------------------- #
def _radial(size):
    c = (size - 1) / 2.0
    yy, xx = np.mgrid[0:size, 0:size].astype(np.float32)
    r = np.sqrt((xx - c) ** 2 + (yy - c) ** 2) / (size / 2.0)
    return r


def make_glow_node(rng):
    size = 512
    r = _radial(size)
    core = np.exp(-(r / 0.17) ** 2)
    glow = np.exp(-(r / 0.40) ** 1.75)
    halo = np.exp(-(r / 0.74) ** 2) * 0.34
    a = np.clip(core * 1.05 + glow * 0.80 + halo, 0.0, 1.0) * smoothstep((1.0 - r) / 0.20)
    heat = np.clip(core + glow * 0.55, 0.0, 1.0)[:, :, None]
    rgb = CYAN[None, None, :] * (1.0 - heat) + np.array([236, 252, 255], np.float32)[None, None, :] * heat
    a *= 255.0
    a[a < 1.0] = 0.0
    return rgb, a


def make_glow_pulse(rng):
    size = 256
    r = _radial(size)
    core = np.exp(-(r / 0.12) ** 2)
    glow = np.exp(-(r / 0.30) ** 2.0)
    halo = np.exp(-(r / 0.56) ** 2) * 0.30
    a = np.clip(core * 1.15 + glow * 0.90 + halo, 0.0, 1.0) * smoothstep((1.0 - r) / 0.20)
    heat = np.clip(core * 1.25 + glow * 0.60, 0.0, 1.0)[:, :, None]
    rgb = np.array([70, 232, 255], np.float32)[None, None, :] * (1.0 - heat) \
        + np.array([246, 255, 255], np.float32)[None, None, :] * heat
    a *= 255.0
    a[a < 1.0] = 0.0
    return rgb, a


# --------------------------------------------------------------------------- #
# 6. scanlines.png
# --------------------------------------------------------------------------- #
def make_scanlines(rng):
    ys = np.arange(H)
    a = np.zeros(H, np.float32)
    a[ys % 3 == 0] = 22.0
    a = np.tile(a[:, None], (1, W))
    rgb = np.zeros((H, W, 3), np.float32)
    rgb[:] = np.array([3, 10, 22], np.float32)
    return rgb, a


# --------------------------------------------------------------------------- #
# 7. cone.png
# --------------------------------------------------------------------------- #
def make_cone(rng):
    xx, yy = coords()
    dy = (H - 1) - yy                       # 0 at the bottom edge, H-1 at the top
    half = 26.0 + 660.0 * (dy / H) ** 1.12  # widens as it rises
    d = np.abs(xx - W / 2.0) / half         # 0 on the axis, 1 at the soft rim

    rim = smoothstep((1.0 - d) / 0.55)
    lat = np.exp(-(d / 0.78) ** 2)
    vfall = np.exp(-dy / (H * 0.52))
    grain = 0.86 + 0.28 * fbm((H, W), rng, 4, (5, 8))

    inten = rim * vfall * (0.30 + 0.70 * lat) * grain
    inten = np.clip(inten, 0.0, None)
    inten /= max(float(inten.max()), 1e-6)

    heat = np.clip(vfall * 1.15, 0.0, 1.0)[:, :, None]
    rgb = np.array([86, 214, 255], np.float32)[None, None, :] * (1.0 - heat) \
        + np.array([168, 244, 255], np.float32)[None, None, :] * heat
    rgb += rng.normal(0.0, 0.35, (H, W, 3)).astype(np.float32)
    return rgb, inten * 132.0


# --------------------------------------------------------------------------- #
# report
# --------------------------------------------------------------------------- #
def report(path):
    im = Image.open(path)
    a = np.asarray(im)
    al = a[:, :, 3]
    print("  %-16s %s %s  alpha[min=%d max=%d mean=%.1f]  transparent=%.1f%%  "
          "nonzero=%.1f%%" % (
              os.path.basename(path), im.mode, "%dx%d" % im.size,
              int(al.min()), int(al.max()), float(al.mean()),
              100.0 * float((al == 0).mean()), 100.0 * float((al > 0).mean())))


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seed", type=int, default=DEFAULT_SEED)
    ap.add_argument("--out", default=os.path.dirname(os.path.abspath(__file__)))
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--only", default=None, help="comma-separated subset")
    args = ap.parse_args()

    out = os.path.abspath(args.out)
    os.makedirs(out, exist_ok=True)
    want = set(args.only.split(",")) if args.only else None

    jobs = [
        ("galaxy.png", "galaxy", make_galaxy),
        ("stars.png", "stars", make_stars),
        ("grid.png", "grid", make_grid),
        ("glow-node.png", "glow_node", make_glow_node),
        ("glow-pulse.png", "glow_pulse", make_glow_pulse),
        ("scanlines.png", "scanlines", make_scanlines),
        ("cone.png", "cone", make_cone),
    ]

    print("make_holo_assets.py  seed=%d  out=%s" % (args.seed, out))
    for fname, tag, fn in jobs:
        key = fname[:-4]
        if want and key not in want:
            continue
        rng = rng_for(args.seed, TAGS[tag])
        rgb, alpha = fn(rng)
        rgba = save(os.path.join(out, fname), rgb, alpha)
        print("  wrote %-16s %dx%d RGBA  mean alpha %.1f"
              % (fname, rgba.shape[1], rgba.shape[0], float(rgba[:, :, 3].mean())))

    if args.report:
        print("report:")
        for fname, tag, fn in jobs:
            if want and fname[:-4] not in want:
                continue
            report(os.path.join(out, fname))
    return 0


if __name__ == "__main__":
    sys.exit(main())
