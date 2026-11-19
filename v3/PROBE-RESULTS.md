# Animated WebP probe on P1 — 16 Nov 2026

Isolated Quickshell window (`~/.cache/holo-webp-probe/` on P1, source in `probe/` here). Live holo (PID 1425) untouched; `shell.qml` hash unchanged before and after.

Media: two 400×960 animated WebPs with smooth alpha, 48 frames at 24 fps, 3.2 MB each. Made by warping one still locally (no video provider). Photographic content, every frame different.

| Case (12 s each) | Delivered fps | CPU (one core) | RSS |
|---|---|---|---|
| Two PNG holds, moving background | background 23.5 | 3.3% | 200 MB |
| One WebP playing | 23.4 | 5.6% | 272 MB |
| Two WebPs playing | 23.3 and 23.3 | 5.5% | 342 MB |
| One-shot, `FinishAtFinalFrame` | both stopped on frame 47 and held | — | 341 MB |

- First play of each file costs about 1 s of CPU while all frames decode into the cache, and about 70 MB per 48-frame clip (matches 400×960×4×48). Preload before swapping from the hold.
- Screenshot mid-run: checkerboard shows through around and between limbs, no rectangle behind the figures. The halos in the shot come from my rough grey key, not from playback.
- Two grabs 0.5 s apart differ in 61% of pixels, so the window was really drawing.

Not tested: inside the live holo config next to the room shader and fleet overlay; real transition footage; `cache: false`; longer clips; repeated transitions.

Other state: Venice returned 402 (no balance) on the clean plate and Lana still; only `gen/mila_A-2e8462.png` rendered. Martin: no Venice for animation until he has administered the account.
