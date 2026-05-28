# CtimeLI

**CLI See Time** — macOS screen-edge countdown for time-blind work.

<p align="center">
  <img src="docs/images/Stroke.png" alt="Stroke" width="32%" />
  <img src="docs/images/Glow.png" alt="Glow" width="32%" />
  <img src="docs/images/Block.png" alt="Block" width="32%" />
</p>

For people who lose track of time mid-task: 10 minutes before a meeting becomes 5 minutes late, or you keep saying "just leave" and don't.

## Features

- Shrinking stroke around every display (click-through, all monitors)
- Edge glow + progressive blur in the final stretch (default: glow 120s, blur 30s)
- HUD with remaining time + Finish button
- Block-on-end: full-screen stop overlay, then hide other apps + minimize focused window
- Watch mode: menu bar Start/Add/Quit; calendar auto-start before events; runs in background after launch
- Calendar sessions: green stroke; manual: blue; retargets if a sooner event appears
- Remote meetings: parses Zoom/Meet/Teams URLs from calendar; opens link at zero when off work Wi-Fi (`WORK_WIFI_SSIDS`)
- In-person meetings: stop overlay shows room from event location

## Install

**Required**

- macOS
- Python 3.11+ (`python3` on PATH)

**Optional permissions** — timers work without them; `./run permissions` any time

| Permission | Unlocks | How |
|------------|---------|-----|
| Accessibility | Block-end window tidy | Alert → System Settings → turn on **Python** |
| Calendar | Watch auto-start from events | **Allow** on the macOS dialog (after `./install.sh` once) |

Run `./install.sh` to set up; it walks through permissions. Re-run `./run permissions` later if you skipped or denied.

```sh
./install.sh
```

Creates `.venv`, installs PyObjC + ctimeli, copies `.env`. Prompts to add `ctimeli` to `~/.zshrc` (runs watch mode). Non-interactive: `INSTALL_ZSHRC=1 ./install.sh`.

```sh
./uninstall.sh
```

Removes `.venv`, `.env`, `apps.manifest`, build caches, and the marked `ctimeli` block from `~/.zshrc` (`# >>> ctimeli >>>` … `# <<< ctimeli <<<`). Non-interactive: `UNINSTALL_YES=1 ./uninstall.sh`.

## Use

```sh
./run 15               # 15-minute timer
./run 6:00pm           # countdown to clock time
./run watch            # watch mode (menu bar + calendar; background)
```

After install, `ctimeli` in a new terminal starts watch in the background (if you said yes to zshrc). Otherwise `./run watch`.

Watch mode: click the menu bar timer icon — **Start timer…** / **Add time…** (when allowed), **Quit watch mode**. Calendar and hard-stop countdowns always take priority over manual timers. You can close the terminal after launch.

If a stuck watch process remains after a crash: `pkill -f "ctimeli watch"`.

Debug foreground (no detach): `CTIMELI_WATCH_FOREGROUND=1 ./run watch`. Log: `~/.cache/ctimeli/watch.log`.

## Development

```sh
./install.sh
.venv/bin/pip install -e ".[dev]"
.venv/bin/pytest
```

## Docs

[`docs/README.md`](docs/README.md) — architecture, features, domain formulas, ports, config.
