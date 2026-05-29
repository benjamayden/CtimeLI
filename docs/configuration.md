# Configuration reference

Configuration is one immutable `AppConfig` value. It is assembled once, at
startup, in this precedence order (later wins):

```
dataclass defaults  <  .env file  <  process environment  <  CLI flags
```

`.env` lives at the repo root. A documented template ships as `.env.example` —
copy it and edit:

```sh
cp .env.example .env
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
| `pulse_before_fraction` | `PULSE_BEFORE_FRACTION` | `0.13333333333333333` | Fraction-remaining where the glow window opens. `PULSE_BEFORE_SECS` is accepted as a compatibility alias. |
| `pulse_opacity_ramp_fraction` | `PULSE_OPACITY_RAMP_FRACTION` | `0.011111111111111112` | Fraction-remaining over which `pulse_max_opacity` is reached. `PULSE_OPACITY_RAMP_SECS` is accepted as a compatibility alias. |
| `pulse_max_opacity` | `PULSE_MAX_OPACITY` | `0.85` | Peak glow alpha, `0..1`. |
| `pulse_depth_min` | `PULSE_DEPTH_MIN` | `10.0` | Glow depth in px at window start (`spread = 0`). |
| `pulse_depth_max` | `PULSE_DEPTH_MAX` | `110.0` | Glow depth in px at zero (`spread = 1`). |
| `pulse_ramp_power` | `PULSE_RAMP_POWER` / `PULSE_RAMP` | `1.0` | Exponent on the spread curve. See below. |
| `pulse_visual_power` | `PULSE_VISUAL_POWER` | `1.0` | Extra draw-time spread shaping (legacy; `1` = off). |

**`PULSE_RAMP` vs `PULSE_RAMP_POWER`.** `PULSE_RAMP` is a named preset:
`linear` → `1.0`, `late` → `3.0`. `PULSE_RAMP_POWER` is the raw exponent and
**overrides** the preset if both are set. The corresponding CLI flags
(`--pulse-ramp`, `--pulse-ramp-power`) follow the same rule.

## Screen blur

| Field | Env key | Default | Meaning |
|-------|---------|---------|---------|
| `blur_before_fraction` | `BLUR_BEFORE_FRACTION` | `0.03333333333333333` | Fraction-remaining where the blur window opens. `BLUR_BEFORE_SECS` is accepted as a compatibility alias. |

Ramp shape follows `pulse_ramp_power` / `PULSE_RAMP` — same exponent as the glow
spread curve. `domain/curves.py::blur_intensity()` is independent of
`pulse_before_fraction`; edge glow and blur can use different windows.

## Block-on-end

| Field | Env key | Default | Meaning |
|-------|---------|---------|---------|
| `block_on_end` | `BLOCK_ON_END` | `false` | At zero, show the stop overlay then tidy windows (Hide Others + Minimize). |

The tidy behaviour is fixed — see [`features.md`](features.md) §8. It requires
Accessibility permission for synthetic keyboard events.

In **watch mode** the host terminal is un-hidden after Hide Others and is never
minimized if it was the focused app.

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

## Work Wi-Fi

| Field | Env key | Default | Meaning |
|-------|---------|---------|---------|
| `work_wifi_ssids` | `WORK_WIFI_SSIDS` | *(empty)* | Comma-separated SSIDs. When connected, remote call links are **not** auto-opened; block-on-end runs normally instead. |

## Hard stop (watch mode)

| Field | Env key | Default | Meaning |
|-------|---------|---------|---------|
| `hard_stop_enabled` | `HARD_STOP_ENABLED` | `false` | Auto-start an end-of-day countdown in watch mode. |
| `hard_stop_time` | `HARD_STOP_TIME` | `22:00` | Local clock time the stroke reaches zero. |
| `hard_stop_warning_mins` | `HARD_STOP_WARNING_MINS` | `30.0` | Orange stroke starts this many minutes before `hard_stop_time`. |
| `hard_stop_stroke_r` | `HARD_STOP_STROKE_R` | `0.95` | Hard-stop stroke base, red channel. |
| `hard_stop_stroke_g` | `HARD_STOP_STROKE_G` | `0.55` | …green channel. |
| `hard_stop_stroke_b` | `HARD_STOP_STROKE_B` | `0.15` | …blue channel. |

---

## CLI flags

### Common to one-shot and watch

Every flag defaults to `None` (= "do not override"). Type is `float` unless
noted. The `--*-secs` names remain accepted as hidden compatibility aliases.

```
--stroke-width            --pulse-before-fraction F    --pulse-opacity-ramp-fraction F
--pulse-max-opacity 0-1   --pulse-depth-min PX         --pulse-depth-max PX
--pulse-ramp {linear,late}                             --pulse-ramp-power N
--pulse-visual-power N    --red-zone-fraction 0-1
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
./run watch                   # watch mode (menu bar + calendar)
./run 25 --block-on-end       # tidy windows at zero
```
