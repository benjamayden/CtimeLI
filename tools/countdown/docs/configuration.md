# Configuration reference

Configuration is one immutable `AppConfig` value. It is assembled once, at
startup, in this precedence order (later wins):

```
dataclass defaults  <  .env file  <  process environment  <  CLI flags
```

`.env` lives next to the app (`tools/countdown/.env`). A documented template
ships as `.env.example` — copy it and edit:

```sh
cp tools/countdown/.env.example tools/countdown/.env
```

> **How it is loaded.** The `.env` file is parsed into a plain mapping by the
> `EnvSource` adapter; it is **not** written into `os.environ`. `AppConfig` is
> built by reading that mapping merged over the real environment. This is a
> deliberate fix — the original `load_dotenv` mutated global state. See
> [`edge-cases.md`](edge-cases.md) #5.

CLI flags are typed `None` by default; only non-`None` flags override. The merge
validates that every override key is a real `AppConfig` field — a typo'd key is
an error, not a silent drop ([`edge-cases.md`](edge-cases.md) #6).

---

## Stroke

| Field | Env key | Default | Meaning |
|-------|---------|---------|---------|
| `stroke_width` | `STROKE_WIDTH` | `6.0` | Perimeter line thickness, px. |
| `red_zone_fraction` | `RED_ZONE_FRACTION` | `0.05` | Fraction-remaining at which the colour starts blending to red. |

## Edge glow (pulse)

| Field | Env key | Default | Meaning |
|-------|---------|---------|---------|
| `pulse_before_secs` | `PULSE_BEFORE_SECS` | `120.0` | Length of the glow window before zero, s. |
| `pulse_opacity_ramp_secs` | `PULSE_OPACITY_RAMP_SECS` | `10.0` | Seconds to reach `pulse_max_opacity` after the window opens. |
| `pulse_max_opacity` | `PULSE_MAX_OPACITY` | `0.85` | Peak glow alpha, `0..1`. |
| `pulse_depth_min` | `PULSE_DEPTH_MIN` | `10.0` | Glow depth in px at window start (`spread = 0`). |
| `pulse_depth_max` | `PULSE_DEPTH_MAX` | `110.0` | Glow depth in px at zero (`spread = 1`). |
| `pulse_ramp_power` | `PULSE_RAMP_POWER` / `PULSE_RAMP` | `1.0` | Exponent on the spread curve. See below. |
| `pulse_visual_power` | `PULSE_VISUAL_POWER` | `1.0` | Extra draw-time spread shaping (legacy; `1` = off). |

**`PULSE_RAMP` vs `PULSE_RAMP_POWER`.** `PULSE_RAMP` is a named preset:
`linear` → `1.0`, `late` → `3.0`. `PULSE_RAMP_POWER` is the raw exponent and
**overrides** the preset if both are set. The corresponding CLI flags
(`--pulse-ramp`, `--pulse-ramp-power`) follow the same rule.

## Window wiggle

| Field | Env key | Default | Meaning |
|-------|---------|---------|---------|
| `shake_wiggle_seconds` | `SHAKE_WIGGLE_SECONDS` | `3.0` | The final N seconds during which the frontmost window wiggles. |
| `shake_max_x` | `SHAKE_MAX_X` | `28.0` | Max horizontal offset, px. |
| `shake_max_y` | `SHAKE_MAX_Y` | `28.0` | Max vertical offset, px. |
| `shake_speed` | `SHAKE_SPEED` | `10.0` | Base oscillation speed. |
| `shake_speed_x` | `SHAKE_SPEED_X` | `10.0` | X-axis frequency multiplier. |
| `shake_speed_y` | `SHAKE_SPEED_Y` | `10.0` | Y-axis frequency multiplier. |
| `shake_smooth` | `SHAKE_SMOOTH` | `14.0` | Motion smoothing rate (`lerp` rate; higher = snappier). |

### Removed legacy keys

The original `AppConfig` carried five fields that were loaded but **never
used** — the timing model moved to the pulse/wiggle curves above and these were
left behind as dead config:

`SHAKE_BEFORE_MINS`, `SHAKE_START_FRACTION`, `SHAKE_NUDGE_SECONDS`,
`SHAKE_NUDGE_LEVEL`, `SHAKE_STOP_BEFORE_MINS`.

They are **removed**. If present in a `.env` they are ignored (unknown env keys
are harmless). See [`edge-cases.md`](edge-cases.md) #7.

## Block-on-end

| Field | Env key | Default | Meaning |
|-------|---------|---------|---------|
| `block_on_end` | `BLOCK_ON_END` | `false` | At zero, show the stop overlay then tidy windows. |
| `block_end_default` | `BLOCK_END_DEFAULT` | `minimize` | Action for foreground apps not on any explicit list. One of `minimize` / `hide` / `quit` / `skip`. |
| `block_end_minimize` | `BLOCK_END_MINIMIZE` | *(empty)* | Comma-separated app names to minimize. |
| `block_end_hide` | `BLOCK_END_HIDE` | *(empty)* | Comma-separated app names to hide. |
| `block_end_quit` | `BLOCK_END_QUIT` | *(empty)* | Comma-separated app names to quit. |
| `block_end_skip` | `BLOCK_END_SKIP` | *(empty)* | Comma-separated app names to leave alone. |

`BLOCK_END_DEFAULT` is validated against the four legal actions; an unrecognised
value falls back to `minimize`.

The full assignment precedence is in [`features.md`](features.md) §8 and the
pure planning algorithm in [`domain.md`](domain.md) §6.

### App-name aliases

Block-end name matching is alias-aware and case-insensitive, so a `.env` can use
the casual name:

| You write | Resolves to |
|-----------|-------------|
| `chrome`, `google chrome` | `Google Chrome`, `Chrome` |
| `settings` | `System Settings`, `Settings` |
| `system preferences` | `System Settings` |
| `iterm` | `iTerm2`, `iTerm` |
| `vscode` | `Code` |
| `terminal`, `apple_terminal` | `Terminal`, `Apple_Terminal` |
| `cursor` | `Cursor` |

### Never-touched apps

Always skipped by block-end, regardless of config (the `SYSTEM_SKIP` set):
`SystemUIServer`, `WindowManager`, `Dock`, `loginwindow`, `Python`, `python`.
In **watch mode** the host terminal is added to the skip set too, so the watcher
never hides the terminal you are still using.

### Never-wiggled apps

Independently of block-end, the wiggle never targets: `Terminal`, `iTerm2`,
`iTerm`, `Warp`, `Cursor`, `Python`/`python`, `SystemUIServer`, `WindowManager`,
`Dock`, `loginwindow`. The current `$TERM_PROGRAM` is added dynamically.

## Calendar

| Field | Env key | Default | Meaning |
|-------|---------|---------|---------|
| `calendar_enabled` | `CALENDAR_ENABLED` | `true` | Master switch for calendar auto-start (watch mode). |
| `calendar_poll_seconds` | `CALENDAR_POLL_SECONDS` | `15.0` | How often the watcher re-queries the calendar. |
| `calendar_window_minutes` | `CALENDAR_WINDOW_MINUTES` | `10.0` | Only events starting within this window are considered. |
| `calendar_block_before_mins` | `CALENDAR_BLOCK_BEFORE_MINS` | `7.0` | The block fires this many minutes before the event start. |
| `calendar_stroke_r` | `CALENDAR_STROKE_R` | `0.30` | Calendar-session stroke base, red channel. |
| `calendar_stroke_g` | `CALENDAR_STROKE_G` | `0.85` | …green channel. |
| `calendar_stroke_b` | `CALENDAR_STROKE_B` | `0.45` | …blue channel. |

---

## CLI flags

### Common to one-shot and watch

Every flag defaults to `None` (= "do not override"). Type is `float` unless
noted.

```
--stroke-width            --pulse-before-secs SEC      --pulse-opacity-ramp-secs SEC
--pulse-max-opacity 0-1   --pulse-depth-min PX         --pulse-depth-max PX
--pulse-ramp {linear,late}                             --pulse-ramp-power N
--pulse-visual-power N    --shake-wiggle-seconds SEC
--shake-max-x  --shake-max-y  --shake-speed  --shake-speed-x  --shake-speed-y  --shake-smooth
--red-zone-fraction 0-1
--block-on-end / --no-block-on-end       (boolean toggle)
```

### One-shot only

| Flag | Meaning |
|------|---------|
| `time` (positional) | Minutes / clock time — see [`features.md`](features.md) §10. |
| `--at HH:MM` | Target time in flag form (equivalent to the positional). |
| `--for-minutes MIN` | Count down N minutes from now. Mutually exclusive with `time`/`--at`. |

### Invocation

```sh
./run 15                      # 15 minutes
./run 6:00                    # next 6 o'clock
./run --for-minutes 25        # explicit minutes
./run watch                   # watch mode (stdin + calendar)
./run 25 --block-on-end       # tidy windows at zero
./shake --seconds 20          # standalone wiggle-tuning harness
```

## Future config (planned, not yet implemented)

From the calendar-calls / hard-stop plan — listed so a port leaves room:
`WORK_WIFI_SSIDS`, `HARD_STOP_ENABLED`, `HARD_STOP_TIME`,
`HARD_STOP_WARNING_MINS`, `HARD_STOP_STROKE_R/G/B`. See
[`features.md`](features.md) §"Future session kinds".
