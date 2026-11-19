# Holodeck v3 — plan (on hold after proof of concept, 17 Nov 2026)

Status: proof of concept done for both women (stand -> showpiece transition, keyed onto the clean plate). Martin has watched both and says it works. Nothing runs on P1; the live holo is untouched.

## Design as it stands
- Two separate assets, one per woman (Lana left of the chair, Mila right), each a portrait clip over the empty plate.
- Hub and spoke: each woman has an idle stand (original throne pose) and three poses. Every pose transitions stand -> pose, and pose -> stand by playing the same clip in reverse (no extra generation cost). Pose to pose goes via the stand.
- Do not preload everything: load only the clip about to play, release it after.
- Poses (3 each, all different):
  - Lana: scorpion (done), reach #12, retire with both arms overhead #84 (still done).
  - Mila: quiet hold #11, open retire #83, unassisted arabesque penchee (shallow version done).

## Open decisions for Martin
1. Facing: which way each woman faces (toward the chair, away, or mirrored). Flipping a clip is free.
2. What triggers which pose (bot state? idle dim and still, working lit and pulsing; where do poses come in?).
3. Clip width and length: 832x1108 at 150 frames is about 550 MB decoded, too much for the WebP frame cache. Candidates: crop to the figure (~600 wide), 24 fps, 3 s clips, or video playback.
4. Mila's penchee: accept the shallow version or redo for a vertical leg.

## Phases
A. Assets. Ballet-named spec per pose (feet, arms, body direction, head, lifted leg). Green stills for the remaining 4 poses, then 4 more transitions. Est. $0.65 per Wan clip plus ~$0.1-0.2 per still; with retries roughly $10-15 total. Compare one transition on Seedance 2.5 Flash (~$0.95).
B. Look. One shared grade script for both women: colour transfer toward the room's cool blue-grey, lower-contrast shadows, cool rim light, soft contact shadow, targeted shadow fix for olive tint under raised legs, same settings for both. Test on both transitions with before and after frames.
C. Format. Decide between (a) WebP frame cache after cropping and lower fps, (b) video playback with a chroma-key shader in QML (untested), (c) VP9/WebM with alpha (untested in Quickshell). Test in an isolated Quickshell window on P1 like the earlier WebP probe.
D. Integration. Test inside the live holo next to the room shader and fleet overlay, with backup and rollback. Check hold-to-clip swap alignment (first and last frames must match the held stills; crossfade a few frames).
E. Behaviour wiring. Map bot states to poses once decision 2 is made.

## Known weak points
- Transition mid-section (Lana frames 60-90 hand-to-foot catch; Mila frames 30-60 dip and turn, 90-110 bent leg).
- Hands are soft or oddly curled in some frames; Seedream is the weak model for hands and feet.
- Video is 720p upscaled ~1.5x onto the 2816x1584 plate.
- Venice credit about $22.9 at last check.

## Files
Project on P1: ~/Projects/Holodeck v3/ (gen/, poses/, out/, probe/, STATUS.md). Overlay bot designs and other Holodeck assets live elsewhere and still need to be gathered in.

## Parked (17 Nov, Martin's call): later, not now
- Overlay glow layer over the plate with the stand-pose figures: `work/paint.py` paints the nets (screen blend), so the glow layer can be rendered alone and screened over the clean plate + keyed figures. The women in `out/02_active.jpg` are baked into the base, so new poses need a repaint on the plate.
- Fable is no longer available; attribution of paint.py's net designs to Fable is unconfirmed.
- Martin wants to avoid draining accounts for now; revisit later.
- Style notes: robotic/android stepped movement (8-12 fps, holds, snaps), a quick pirouette then glowing eyes (glow as an overlay layer, not video), and held stills read as intentional for statue/android figures. Full-scene render (background included) played straight over the desktop is another option to try.

## Next session: brightness model (Martin, 19 Nov)
Martin: "keep things lit up but still react to pulses... like 50% brightness until active, and a brief brightness pulse upon receiving a pulse."
- Floor: every known net at 50% (offline, idle, unknown alike); offline vs idle told apart by motion only (still vs breathing). Default unless Martin says otherwise.
- Working: ramp to 100%, ease back to 50% over ~2 s when it stops.
- Pulse lands: receiving net flashes to 100% for ~1 s (fast attack, ~0.8 s decay) plus a small spike burst from the landing node; sender gets a softer kick on departure.
- Same rule for the Hindsight ring and the floor waveguides (50% floor, flash when a pulse passes or lands).
- Code: shell.qml targetLevel() floor + an impact term per net from particle arrivals (displayAt + 6 s), NetView.burst() on landing. Opacity only, so no CPU cost.
- Then decide cuts (seat lip, kaomoji words, diamonds) after seeing it.
