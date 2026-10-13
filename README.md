# Holodeck

A Quickshell, click-through desktop background that visualizes a local/remote AI agent fleet: breathing nodes, hierarchy links, drifting positions and event-timed communication particles.

This is the **renderer**, not a complete Hermes telemetry integration. Collectors and remote beacon services are not included. The initial layout retains the original P1/VPS naming conventions (including Mila/Lana); adapt `Renderer.js` for your fleet. No live telemetry, personal photos, credentials or historical backups are included.

## Requirements

- Linux Wayland compositor supporting wlr-layer-shell (developed on Hyprland/Omarchy).
- Quickshell with QtQuick, Quickshell.Wayland and Quickshell.Io.
- Noto Sans Mono recommended.
- Python 3, NumPy and Pillow for procedural assets; Node.js for tests.
- `pgrep` and `setsid` for the optional toggle launcher.

## Install

Review before copying: these commands replace an existing installation's source files.

```sh
git clone https://github.com/martyllmaccs-hash/holodeck.git
cd holodeck
python3 -m venv .venv
.venv/bin/pip install numpy Pillow
.venv/bin/python assets/make_holo_assets.py
.venv/bin/python -c 'from PIL import Image; Image.open("assets/galaxy.png").convert("RGB").save("assets/background.jpg")'
mkdir -p "$HOME/.config/quickshell/holo/assets" "$HOME/.local/bin"
cp shell.qml HoloNode.qml Renderer.js Drift.js "$HOME/.config/quickshell/holo/"
cp assets/*.png assets/background.jpg "$HOME/.config/quickshell/holo/assets/"
install -m 755 holo-widget holo-toggle "$HOME/.local/bin/"
"$HOME/.local/bin/holo-widget"
```

Launch from your existing Wayland session so its display environment is inherited. `holo-toggle` starts or dismisses the background. Logs go to `${XDG_STATE_HOME:-$HOME/.local/state}/holo-widget.log`.

The layout was designed around 1920×1080. Configuration and telemetry paths currently use `$HOME/.config` and `$HOME/.local/state`, not the corresponding XDG overrides. You may replace `assets/background.jpg` with your own image; private reference images are deliberately excluded.

## Telemetry contract

The renderer reads these JSON files every two seconds:

- `$HOME/.local/state/holo/fleet.json`: local `p1` nodes, snapshot timestamp `ts` (Unix seconds).
- `$HOME/.local/state/holo/beacon-vps.json`: remote `vps` nodes, timestamp `beacon_ts`. A fresh standalone beacon is authoritative; merged remote rows in the local fleet snapshot are not a substitute.

Snapshots contain a `nodes` array. Nodes have `id` and `machine`; hierarchy uses same-machine `parent_id`. Local snapshots expire after 30 seconds and remote snapshots after 180 seconds. Without a producer, expect no local nodes and an `UNLINKED` remote placeholder. Consult `renderer.test.cjs` for synthetic fixtures and the explicit communication-event contract. Those fixtures are tests, not live activity.

## Checks

```sh
node --test renderer.test.cjs
sh -n holo-widget holo-toggle
```

The initial publication passed all eight renderer tests and launcher syntax checks. QML GUI behavior in this sanitized checkout has not been exercised; the original running desktop configuration is separate and unchanged.

## Sharing and licensing

This repository is public for inspection and sharing. No open-source license has been selected yet; public visibility alone does not grant a general redistribution or modification license.
