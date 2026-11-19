# Holodeck v3

Sci-fi chamber desktop background for the P1 Quickshell fleet overlay: Lana and Mila as separate
figure layers that go dormant/attention with node state, live nets, event pulses, Hindsight drum.
Status and design notes: `STATUS.md`, `PLAN.md`. Previews: `04_v3_live_static.jpg`, `05_v3_preview_active.jpg`.
The v1/v2 holo lives at the repo root, untouched.

## Layout
- `build/holo-v3/` — the runtime (shell.qml, Figure.qml, NetView.qml, Scene.js, Renderer.js, assets/). Copy to `~/.config/quickshell/holo-v3`.
- `build/holo-v3-launch`, `build/holo-switch` — launcher and golden/v3 switcher (`~/.local/bin`).
- `build/build_assets.py`, `build/build_figures.py` — regenerate every layer and figure clip.
- `work/` (`paint.py` approved mockup, `source.jpg` room render), `crop/`, `gen/` — build inputs, incl. the Wan dormant->attention clips.
- `bridge/` — VPS side that feeds the overlay (producer, receiver, runtime_bridge, memory_events). `HINDSIGHT_HOST` in `memory_events.py` is a placeholder for the Hindsight host.
- `build/p1-collector` — P1-side collector.

## Run
`quickshell -n -p ~/.config/quickshell/holo-v3`  (or `holo-v3-launch`)

## Rebuild assets
`python build/build_assets.py` then `python build/build_figures.py lana|mila` (needs numpy, opencv, scipy, Pillow).
Run from the v3 folder layout; scripts expect `work/`, `crop/`, `gen/` beside `build/`.
Not included: raw generation output, pose reference photos, the Python venv.
