# Holodeck v3 — status, 17 Nov 2026

## Pipeline proven (Lana, one transition)
1. Green-screen stills, 3:4 portrait, flat #00B140, no floor line. Made with Venice edit models from `gen/lana_A-622ce8.png` (identity ref).
   - Stand (original throne pose): `gen/lana_stand_green-8b8691.png` (seedream-v5-5-edit, ~$0.05)
   - Scorpion: `gen/lana_scorpion_green-08c056.png` (nano-banana-2-1-edit, ~$0.14, pose guide = real-dancer photo `gen/scorpion_ref_photo.png`, private reference only)
2. Transition: Wan 3.0 image-to-video with first+last frame (`wan-3-0-image-to-video`, 5s, 720p, 3:4, ~$0.65, ~90s render) -> `gen/transition_stand_to_scorpion_wan3.mp4` (832x1108, 30fps, 150 frames).
3. Key + place on clean plate with `gen/comp_keyer.py` (placement from original: x 475-887, feet y 1531, height 1377 of 1584) -> `gen/transition_on_plate.mp4`. Martin watched it: works.

## Known issues / next
- Despill (olive cast under raised thigh, pale green tint on corset, thin green edge), relight to the cool room, add contact shadow.
- Weak frames 60-90 (lifted-leg shape, overhead hand clipped at 70, hand-to-foot catch at 80).
- Resolution: 832 wide upscaled ~1.56x; 150 frames decoded ~550 MB, too big for the WebP frame cache. Options: crop to figure, <=24 fps, shorter, or video playback. Do NOT preload every clip; load only the next one.
- Venice balance after this session about $23.

## Pose plan (3 each)
Lana: scorpion, reach (#12), arms-raised retire (#84; proof of concept `gen/lana_pose84-46a48d.png`).
Mila: quiet hold (#11), open retire (#83), arabesque penchee (unassisted, straight back leg vertical, torso tipped forward).
Notes: pose ref sheets and Google screenshots in `poses/`. Keep the ballet-term spec per pose: feet, arms, body direction, head, lifted leg.

## Not tested
Inside the live holo next to the room shader and fleet overlay; Mila's transitions; second video model for comparison; hold-to-clip swap alignment.

## Dormant -> attention (19 Nov) — NO green screen, real background
Design (Martin): bots stand dormant (arms low, slightly open, head turned away and down; Lana looks screen-left, Mila screen-right), then come to attention = the ORIGINAL render pose (hands behind hips, elbows out). Reverse playback = back to dormant.
- Crops from `work/source.jpg` (2816x1584): 900x1584, Lana x 231-1131, Mila x 1666-2566. `crop/{lana,mila}_og_900.png` = attention frame (untouched original).
- Dormant stills: nano-banana-2-1-edit, crop + `poses/twins_dormant_ref.png` (Atomic Heart frame, private pose ref only), prompts `gen/dormant_{lana,mila}.txt`. Figure cut with Venice /image/background-remove, pasted onto the original crop; old-pose region filled from `gen/plate-d72d79.png` (pixel-aligned clean plate). Finals: `crop/{lana,mila}_dormant_final.png`. Background outside the figures = identical to original (measured diff 0).
- Lana clip: Wan 3.0 first/last frame (dormant -> og), 9:16 720p 5s 30fps 150 frames, ~$0.65: `gen/transition_lana_dormant_to_attention_wan3.mp4` (raw, 720x1280). Script: `/opt/data/cache/scratch/venice_video_dormant.py <name> <left|right>` (pipe bws JSON in).
- Background sway measured: <=3 px at one frame, 0 at end; effectively none. Locked version anyway: clip only inside feathered figure mask `crop/lana_motion_mask.png`, original room outside: `gen/lana_dormant_to_attention_locked.mp4` (900x1584, place at x 231, y 0 on the plate). In-context preview: `gen/lana_dormant_to_attention_wallpaper_preview.mp4` (1408x792).
- Martin approved: usable asset. Mila clip not yet run (same script, `mila right`).
- Venice key: use BWS VENICE_API_KEY (new account); the process env copy is the old empty account until Hermes restarts.

## Mila transition (17 Nov, later)
- Green stills: `gen/mila_stand_green-0c20c7.png` (seedream-v5-5-edit), `gen/mila_penchee_green-3e8811.png` (nano-banana-2-1-edit, text-only pose; raised leg ~60-65 deg off floor, slight knee softness, torso near-horizontal: shallow penchee).
- Transition: `gen/transition_mila_stand_to_penchee_wan3.mp4` (Wan 3.0, 5s, 720p, ~$0.65). On plate: `gen/transition_mila_on_plate_despill.mp4` (placement x centre 2116, feet y 1514, height 1339).
- Weak frames about 30-60 (bent-knee dip, abrupt rise and turn at ~50, proportion drift) and 90-110 (leg still bent).

## v3 built and live (19 Nov 2026), Lana and Mila static
- **Running on P1** as the desktop background: `quickshell -n -p ~/.config/quickshell/holo-v3` (layer `holo-v3`, Background). Golden holo stopped, files untouched.
- Switch: `holo-switch v3` / `holo-switch golden` / `holo-switch status` (~/.local/bin). Autostart (`~/.config/hypr/autostart.lua`) still launches golden at login: not changed.
- Source: `build/build_assets.py` (makes every layer from `work/paint.py`, the approved mockup) -> `build/holo-v3/` (shell.qml, Scene.js, Renderer.js copied unchanged from golden, assets/). Checksums in `~/.config/quickshell/holo-v3/SHA256SUMS` on P1.
- Live signals: net brightness = node state (working / idle / offline / unknown); twinkle = working; points of light = real message/handoff events (same Renderer.js rules as golden); prisms = `tool_active` or tool-state word; seat lip = Lana or Mila going from not-working to working; thinking glyphs above whichever sister is working.
- **Not wired:** Hindsight drum write arc reads `memory.last_write_ts` from fleet/beacon, which no producer sends yet, so it never lights on real data. VPS beacon has no `tool_active`, so Lana-side prisms only light on tool-state words.
- Debug IPC (display only): `quickshell ipc -p ~/.config/quickshell/holo-v3 call holov3 preview 30|probe|status|snapshot /tmp/x.png`.
- `figdemo lana|mila <cycles>` (19 Nov, deployed): plays fall + rise pairs from the resting pose, 2 s apart, ignoring fleet state (Lana's default node stays RUNNING while a desktop session is open, so she never goes dormant on her own). Use it to eyeball alignment. Fixed 19 Nov: Lana's Wan clip ended with her upper body ~4-8 stage px LEFT of base.jpg (Martin: "Alert is slightly to the right"), then snapped right. `build_figures.py` SETTLE warps frames 80-150 toward the original with smoothed flow; frame 142 offset -4.4 -> -0.6 px. Deployed to P1 live assets (old clips in `gen/fig_lana_prewarp/` and P1 `~/.cache/holo-v3-stage/prewarp/`). Mila <0.5 px, untouched. Colour fix 19 Nov: Wan drifted Lana's body colour (f1 -3.5 levels vs the dormant still, warming to +5 R mid-rise, snapping back in its last 2 frames). `COLOUR` in build_figures grades each frame so her body-core mean glides dormant -> Alert (R peak 109 -> 103, max step 2.0 -> 0.9). Tested on the live holo with static clips: Qt honours colour tags, untagged = BT.601, and every TV-range encoding (601/709/4:4:4) matches the still within ~1.8/255, so the encoding is fine as is. Pre-fix clips are in `gen/fig_lana_precolour/`.
- Measured: ~15% of one core steady, 247 MB RSS (golden was ~23%, 345 MB). Renders: `out/04_v3_live_static.jpg` (real data), `out/05_v3_preview_active.jpg` (preview + probe pulses).

## v3.1 (19 Nov 2026): animated nets + Hindsight pulses
- Nets are live (`build/holo-v3/NetView.qml`): pre-rendered crisp net breathes (GPU scale/sway), spikes run along the real edges in cascades and flash the nodes they land on. Offline = still, idle = slow breathe + rare spark, working = cascades scaled by activity. Derpy one's eyes blink and glance (tiny Canvas, repainted only then).
- CPU: 9% of one core live (only Lana working), 12% with everything firing; 266 MB. A per-frame Canvas version cost 65%, so don't go back to repainting nets.
- Hindsight: VPS bridge (`/opt/data/holo/memory_events.py`, hooked into `runtime_bridge.py`; backup `/opt/data/backups/holo-bridge-20261118T225421Z`) adds a `hindsight` node and E events. retain = default->hindsight (warm point along Lana's ceiling line into the drum, write arc lights); recall = hindsight->default (ring flashes cool, point runs out, Lana's core fires). Explicit tool calls are observed; per-turn auto-recall (first LLM call of a turn) and auto-retain (turn stops refreshing for 8 s) are inferred from Hindsight's hybrid mode. Drum dims if `/health` fails. Only Lana's profile has Hindsight; Mila has none.
- Verified: real `hindsight_recall` arrived on P1 beacon as `mem.recall.tool.*` hindsight->default; probe IPC `holov3 memprobe` shows the full retain/recall sequence. Not yet seen on screen from a real event (only via probe).
- Golden holo would now show an extra "Hindsight" node from the beacon.
- P1 backup of v3.0: `~/.config/quickshell/holo-v3.bak-20261119T100302`.
- Open: placement B (sternum) glyphs not used; staff labels are faint 9 px text; walls are busier than the mockup because Lana has 7 specialists + playroom.

## v3.2 (19 Nov 2026): dormant / attention states live
- Each sister is dormant (arms low, head away) until her node is `working`, then plays dormant->attention; after 20 s without work she plays it back to dormant. Attention = base.jpg itself (original pose), so awake costs nothing. A clip always finishes before the next decision; boot picks the pose with no clip once fleet + beacon have arrived.
- Mila clip: `gen/transition_mila_dormant_to_attention_wan3.mp4` (Wan 3.0, same script `mila right`, ~$0.65). Contact sheet `crop/mila_clip_sheet.jpg`: one woman, feet planted, clean.
- `build/build_figures.py lana|mila` -> `holo-v3/assets/fig_<n>_dormant.jpg`, `fig_<n>_rise.mp4`, `fig_<n>_fall.mp4` (618x1080, stage boxes Lana x 156, Mila x 1134). Frames are room-locked with the motion mask, frame 0 = the dormant still, last 8 frames ease onto the exact original, then graded with paint.py's grade (incl. vignette, at the crop's position) and LANCZOS-scaled exactly like base.jpg. Seam check: dormant vs base outside the figure 0.69/255 mean; last frame vs base 1.2 mean (JPEG noise).
- `build/holo-v3/Figure.qml` (QtMultimedia MediaPlayer + VideoOutput; P1 has qt6-multimedia-ffmpeg 6.12). Decoder freed after each clip. shell.qml: two Figure items right above base.jpg, so all overlays stay on top; `status` IPC reports `figures`.
- Verified on P1: boot lana=awake / mila=dormant with no clip; `preview 12` -> mila rise -> awake -> (preview end + 20 s) fall -> dormant; mid-rise snapshot shows a real video frame. RSS ~315 MB at rest, ~590 MB while a clip plays, ~380 MB after. CPU 16.8% of a core measured over 5 s with Lana working (earlier 9-12% figure not A/B-checked against this build).
- IPC from ssh needs `XDG_RUNTIME_DIR=/run/user/1000` and `quickshell ipc --pid <pid> ...` (`-p` reported "no running instances").
- P1 backups: `~/.config/quickshell/holo-v3.bak-20261118T235024Z` (v3.1), `.bak-20261118T235529Z`. Golden untouched; autostart still golden.
- Not yet seen: Lana's fall on a real end-of-turn (watch it), Mila rising from a real Mila turn.

## v3.3 (19 Nov 2026): throne double-click = full fleet smoke
- Double-click the throne (stage x 830-1090, y 420-1040; the only input region of the layer, so it works only when the throne is not under a window) -> `~/.local/bin/holo-smoke` on P1 (source `build/holo-smoke`). 10-min cooldown (`--force` overrides). IPC: `holov3 smoke`, `holov3 smokeStatus`.
- P1 half: Mila takes a real `hermes chat -q` turn that `a2a_call`s Lana; staff1-4 get attributed Bot Mode one-word pings from Mila. VPS half: Lana (A2A turn) runs `/opt/data/holo/holo_smoke_vps.py <run>` detached (Bot Mode pings from Lana to 8 VPS profiles, staggered 3 s, plus Hindsight /health), does hindsight_recall + retain, and the script writes `~/.local/state/holo/smoke-vps.json` on P1 over ssh. Results: `smoke-p1.json`, readout line at y 1030 ("SMOKE <run> · n/15 · ✗ ..."), VPS copies in `/opt/data/holo/smoke-results/`.
- A2A passes only if the VPS half reports for that run (Mila's -q output echoes the prompt; the first build falsely passed on it).
- First real results (runs T1, 113500, 113921): researcher, analyst, architect, librarian, playroom, Hindsight OK. auditor + news: Codex subscription 429 (~35 h). ride-test: "profile authority is not ready". staff1-4: `meituan/longcat-2.5-preview:free` withdrawn (HTTP 404). A2A: gateway Lana (default profile, `openai-codex` gpt-6.1-terra) rate-limited, so the VPS half never starts from the throne. Mila OK.
- Collector gap FIXED (19 Nov 13:33): one-shot `hermes chat -q` sessions (ids `local-...`, source oneshot) carry no `turn_id` since 7 Nov, and `runtime_bridge.Tracker.accept` rejected every such row. Patch in `~/.local/share/holo/runtime_bridge.py` on P1: missing turn_id on a `local-` session = turn "oneshot" (one-shot = one turn); nothing else loosened. Backup `runtime_bridge.py.bak-20261119T133307`, copy `build/p1-collector/runtime_bridge.py`. Replay of run 113921: 8/8 rows rejected before, accepted after. tests/test_communication.py: 14 pass, 1 fail (`test_collector_merges_cross_host_a2a_without_machine_guessing`, line 145), identical before and after, so pre-existing. Live: one-shot Mila turn went OFFLINE -> THINKING -> RUNNING -> OFFLINE, figure rise -> awake -> fall (20 s hold) -> dormant.
- Collector restart cost: the reader re-reads `runtime-p1-mila.jsonl` (16 MB, never rotated) from 0 at 64 KB per 2 s tick, so Mila shows UNLINKED for ~9 min after every collector restart. Not changed.
- Never put the quickshell path in a command line that also runs restart.sh: its pgrep matched the ssh session and killed it. Run tests from uploaded scripts.

## Wishlist (Martin, 19 Nov 2026)
- DONE 19 Nov: Lana's status line is now the Hermes CLI vocabulary (KawaiiSpinner thinking/waiting faces + thinking verbs + tool-registry emojis 📖🔎✍️💻🔀), a fresh pick only when the reported state changes, 350 ms crossfade. The braille spinner and the dot row are removed (they moved on a clock, not on data). `status` IPC now reports `glyphs`. Verified live: THINKING -> "٩(๑❛ᴗ❛๑)۶ reflecting…", RUNNING -> "♪(´ε` ) 💻 running…" (colour emoji renders, no tofu). Still clock-driven elsewhere: prism shimmer sin(t*9), floor/drum breathing.
- Polish Lana's status animations further, if wanted.
- Soften or redesign the bright pulse when a signal hits a bot node.
- Mila's neural net: possibly a new shape, ideally one Mila designs herself (geometry format = nodes/edges/tend/core in Scene.js `nets[].geo`). Ask her; it's her call.
- Share-ready clip of the sisters (after Mila agrees to appear).
