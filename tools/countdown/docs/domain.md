# Domain — the pure logic spec

Everything here is **pure**: deterministic, no I/O, no platform calls, no
ambient clock. Time and configuration enter as parameters. This is the part you
port *verbatim* into another language — the formulas do not change.

Notation: `clamp(x, lo, hi)` = `max(lo, min(hi, x))`. All times are seconds
unless noted. `cfg` is the [`AppConfig`](configuration.md).

---

## 1. Math primitives — `domain/math.py`

### `smoothstep(t) -> float`
The S-curve used for every ramp in the app.
```
t  = clamp(t, 0, 1)
return t * t * (3 - 2t)
```
Properties: `smoothstep(0)=0`, `smoothstep(1)=1`, `smoothstep(0.5)=0.5`,
zero first-derivative at both ends (no visible "snap").

> **Smell fixed.** The original defined `_smoothstep` twice — in `countdown.py`
> and in `config.py`. There is now exactly one definition. See
> [`edge-cases.md`](edge-cases.md) #2.

### `lerp(current, target, dt, rate) -> float`
Frame-rate-independent exponential approach. Used for stroke smoothing and
wiggle motion.
```
alpha = 1 - exp(-rate * dt)
return current + (target - current) * alpha
```
Why this and not `current + (target-current)*k`: the `exp(-rate*dt)` form gives
the *same convergence per wall-clock second* regardless of frame rate, so the
animation looks identical at 30 Hz and 120 Hz. `rate` is "per second"; larger =
snappier.

> **Smell fixed.** `_lerp` was duplicated in `countdown.py` and `shake_test.py`.
> One definition now; the shake harness imports it.

### `format_duration(seconds) -> str`
```
s = max(0, int(seconds))              # clamp negatives, truncate
h, rem = divmod(s, 3600)
m, s    = divmod(rem, 60)
if h: return "{h}h {m}m {s}s"
if m: return "{m}m {s}s"
return "{s}s"
```
Examples: `3725 → "1h 2m 5s"`, `64 → "1m 4s"`, `9 → "9s"`, `-5 → "0s"`.

### `clamp(x, lo, hi) -> float`
`max(lo, min(hi, x))`. Provided once; used pervasively.

---

## 2. Animation curves — `domain/curves.py`

All three take `remaining` (seconds left) and `cfg`, and return a number the
overlay renders directly. They are independent — opacity, spread and wiggle do
not reference each other.

### The pulse window

The "pulse" (edge glow) is active only near the end:
```
window  = max(1, cfg.pulse_before_secs)          # default 120
active  = 0 < remaining <= window
elapsed = window - remaining                     # time since the window opened
```
If `not active`, both pulse curves return `0`.

### `pulse_opacity(remaining, cfg) -> float`  →  range `0 .. pulse_max_opacity`
How bright the glow is. Ramps in fast, then holds.
```
if not active: return 0
ramp = max(0.5, cfg.pulse_opacity_ramp_secs)     # default 10
u    = min(1, elapsed / ramp)
return cfg.pulse_max_opacity * smoothstep(u)
```
So the glow reaches full brightness `ramp` seconds into the window and stays
there. `max(0.5, …)` guards a divide-by-zero / instant-pop if the config sets
the ramp to 0.

### `pulse_spread(remaining, cfg) -> float`  →  range `0 .. 1`
How deep the glow reaches inward. Grows across the **entire** window.
```
if not active: return 0
t = clamp(elapsed / window, 0, 1)
return t ** cfg.pulse_ramp_power                  # 1 = linear, 3 = late/cubic
```
`pulse_ramp_power` lets the deepening feel linear or back-loaded. The renderer
maps spread `0..1` onto pixel depth `pulse_depth_min .. pulse_depth_max`.

### `blur_intensity(remaining, cfg) -> float`  →  range `0 .. 1`
Full-screen blur strength. Shares the glow window and spread ramp.
```
if remaining <= 0: return 1
return pulse_spread(remaining, cfg)
```
At the glow window edge → 0; at zero → 1. Shape follows `pulse_ramp_power`.

### Deleted: `pulse_intensity`
The original kept `pulse_intensity` as a "deprecated alias" that just called
`pulse_spread`. Dead code — removed. Callers use `pulse_spread`.

---

## 3. Colours — `domain/colors.py`

### `RGB`
An immutable `(r, g, b)` triple, each channel `0..1`.

Constants:
```
STROKE_BLUE = (0.20, 0.75, 1.00)     # manual session base
STROKE_RED  = (1.00, 0.12, 0.12)     # red-zone / zero
```
Calendar base (green) and any future kind's base come from `cfg`
(`calendar_stroke_r/g/b`).

### `stroke_color_for_fraction(fraction, red_zone, base) -> RGB`
Blends the base colour toward red as the stroke runs out.
```
if fraction > red_zone:
    return base
t = smoothstep(1 - fraction / red_zone)           # 0 at edge of zone, 1 at zero
return RGB(
    base.r + t*(STROKE_RED.r - base.r),
    base.g + t*(STROKE_RED.g - base.g),
    base.b + t*(STROKE_RED.b - base.b),
)
```
`red_zone` is `cfg.red_zone_fraction` (default `0.05`). The blend is per-channel
linear, gated by a smoothstep on `t`.

---

## 4. Time parsing — `domain/timespec.py`

Converts user text into a target `datetime`. **The functions take an explicit
`now` parameter** — they do not call the clock. (The original read
`datetime.now()` internally, which made them untestable; passing `now` in is the
fix. See [`edge-cases.md`](edge-cases.md) #4.)

### Regexes
```
TIME_RE            = ^(\d{1,2})(?::(\d{2})(?::(\d{2}))?)?\s*(am|pm|a\.m\.|p\.m\.)?$   (case-insensitive)
MINUTES_ONLY_RE    = ^\d{1,4}$
DECIMAL_MINUTES_RE = ^\d+\.\d+$
```

### `parse_target_time(raw, now) -> datetime`
Parses a **clock time** into the next future occurrence.

1. Match `TIME_RE` on `raw.strip()`. No match → `ValueError` with a helpful
   message (`"try 6:00, 18:00, or 6:00pm"`).
2. Extract `hour`, `minute` (default 0), `second` (default 0), `meridiem`.
3. Validate: `minute < 60`, `second < 60`, `hour <= 23` → else `ValueError`.
4. **With am/pm**: require `1 <= hour <= 12`. `pm` and `hour != 12` → `+12`;
   `am` and `hour == 12` → `0`. Build today at that time; if `<= now`, add a day.
5. **No meridiem, `hour >= 13`**: unambiguous 24-hour time. Build; roll to
   tomorrow if `<= now`.
6. **No meridiem, `hour <= 12`**: ambiguous. Build *both* candidates
   `{hour%12, hour%12 + 12}`, roll each to the future, return the **nearest**.

### `parse_quick_input(raw, now) -> datetime`
The parser the CLI and watch stdin both use.
```
s = raw.strip()
if s is empty:                       -> ValueError("Empty input")
if MINUTES_ONLY_RE matches s:        -> now + minutes(int(s))
if DECIMAL_MINUTES_RE matches s:     -> now + minutes(float(s))
otherwise:                           -> parse_target_time(s, now)
```

### Parsing edge cases (these must round-trip identically in any port)

| Input | Result | Why |
|-------|--------|-----|
| `6` | now + 6 **minutes** | Bare digits are minutes — the minutes check runs *before* the clock check. |
| `0.5` | now + 30 s | Decimal minutes. |
| `6:00` | next 06:00 or 18:00, whichever is sooner | Ambiguous hour ≤ 12 → nearest candidate. |
| `18:00` | next 18:00 | hour ≥ 13 → unambiguous. |
| `12:00` | next 00:00 or 12:00, whichever is sooner | `12 % 12 = 0` → candidates `{0, 12}`. Noon **or** midnight. |
| `0:30` | next 00:30 or 12:30, whichever is sooner | Same ambiguity at hour 0. |
| `6:00pm` | next 18:00 | Meridiem forces it. |
| `13:00pm` | `ValueError` | hour > 12 with a meridiem is invalid. |
| `6:60` | `ValueError` | minute ≥ 60. |
| `5.` / `.5` | `ValueError` | Matches neither minutes regex; `TIME_RE` rejects it. |
| `9999` | now + 9999 min (~6.9 days) | Accepted — no upper bound. Documented, not guarded. |

---

## 5. Calendar logic — `domain/calendar.py`

### `CalendarEvent` (immutable)
```
event_id: str        # stable EventKit identifier; fallback "{title}:{start}"
title:    str        # "Event" if the source has none
start:    datetime   # local time
call_url: str | None # meeting URL (Zoom/Meet/Teams), if any
room:     str | None # physical room from location, if not URL-like
```

### `calendar_block_target(event_start, cfg, now) -> datetime | None`
When the *block* (zero) should fire for an event.
```
block_at = event_start - minutes(cfg.calendar_block_before_mins)   # default 7
if block_at > now:     return block_at    # normal: countdown ends at buffer
if event_start > now:  return event_start # late: buffer passed, count to event start
return None                               # event already started — nothing to do
```
Normally the timer reaches zero `calendar_block_before_mins` minutes *before*
the meeting, leaving a buffer to arrive. If that buffer window has already
passed but the meeting hasn't started, the countdown fires to the event start
itself so the user always gets a signal. Returns `None` only once the event
has already started.

### `hard_stop_target(cfg, now) -> datetime | None`
Returns today's hard-stop datetime when `now` is inside
`(hard_stop_time − warning_mins, hard_stop_time]`. Returns `None` when disabled,
before the window, or after hard stop has passed.

### `hard_stop_stroke_base(cfg) -> RGB`
Orange stroke base for `SessionKind.HARD_STOP`.

### `is_work_wifi(ssid, work_ssids) -> bool`
Pure membership check — the SSID comes from the `WifiSource` port.

### Event selection (in the adapter, but the rule is domain policy)
The nearest **accepted** event whose start is in `(now, now + window]` where
`window = cfg.calendar_window_minutes` (default 10). "Accepted" =
no attendees, or you are the organiser, or your participant status is
*accepted / tentative / unknown* (declined events are skipped).

---

## 6. Block-end tidy — adapter only

There is no domain planning step. After the stop overlay dismisses,
`SessionRunner._run_cleanup()` activates the pre-block frontmost app and calls
the [`WorkspaceTidy`](ports.md) port:

1. Option+⌘+H — hide every other app.
2. Un-hide watch-mode `extra_skip` apps (host terminal).
3. ⌘+M — minimize the front window unless the front app is skipped.

Requires Accessibility permission for synthetic keyboard events. See
[`features.md`](features.md) §8.

---

## 7. Session state machine — `domain/session.py`

The original lifecycle was five interdependent booleans. It is now one explicit
enum plus a transition function. This is the contract a port must reproduce
*exactly*.

### `SessionKind`
`MANUAL` | `CALENDAR` | `HARD_STOP`. Selects the stroke base colour and the HUD
label format.

Session metadata (calendar only): `call_url`, `room`. Remote call sessions skip
block-on-end when off work Wi-Fi (`skips_block_for_remote_call(on_work_wifi)`).

### `SessionState`
| State | Meaning |
|-------|---------|
| `PENDING` | Constructed; overlays not shown. |
| `RUNNING` | Counting down; producing `RenderFrame`s. |
| `BLOCKING` | Target hit (or finished) with `block_on_end`; stop overlay up. |
| `CLEANUP` | Stop overlay dismissed; block-end plan being applied. |
| `DONE` | Terminal — finished naturally. |
| `INTERRUPTED` | Terminal — `Ctrl+C` / `stop()`. |

### `RenderFrame` — the entire UI contract
What the domain hands the overlay each tick. Plain data, no behaviour:
```
fraction:      float   # 0..1 — smoothed stroke length
label:         str     # HUD text, already formatted
color:         RGB     # stroke colour (red-zone blend already applied)
pulse_opacity: float
pulse_spread:  float
pulse_phase:   float   # animation phase, advances dt*0.85 per tick
blur:          float   # 0..1 screen blur (ScreenBlur port)
```
The overlay renders a `RenderFrame` and asks the domain nothing. Adding a visual
= adding a field here.

### Transition table

| From | Event | Guard | To | Side effect |
|------|-------|-------|----|-----|
| `PENDING` | `start()` | — | `RUNNING` | overlays shown |
| `RUNNING` | `tick(now)` | `now < target` | `RUNNING` | new `RenderFrame` |
| `RUNNING` | `tick(now)` | `now >= target` ∧ `block_on_end` ∧ ¬remote-call skip | `BLOCKING` | stop overlay shown; stroke/HUD hidden |
| `RUNNING` | `tick(now)` | `now >= target` ∧ (¬`block_on_end` ∨ remote-call skip) | `DONE` | remote-call skip: open URL off work Wi-Fi (runner) |
| `RUNNING` | `finish()` | `block_on_end` | `BLOCKING` | as above |
| `RUNNING` | `finish()` | ¬`block_on_end` | `DONE` | — |
| `RUNNING` | `retarget(t')` | `t' > now` | `RUNNING` | see §"Retarget" |
| `RUNNING` | `interrupt()` | — | `INTERRUPTED` | — |
| `BLOCKING` | `dismiss()` | — | `CLEANUP` | — |
| `BLOCKING` | `interrupt()` | — | `CLEANUP` | `interrupted` flag set; still tidies |
| `CLEANUP` | `cleaned()` | — | `DONE` | block-end summary emitted |

Notes:
- `interrupt()` in `BLOCKING` does **not** skip the tidy — the original treats
  `Ctrl+C` while blocked as "dismiss", so windows still get tidied. The flag is
  recorded so the exit message differs. Preserve this.
- Events on terminal states (`DONE`, `INTERRUPTED`) are no-ops.
- `finish()` and `tick()`-at-zero share one decision (`block_on_end ? BLOCKING :
  DONE`) — implement it once.

### Retarget

`retarget(new_target, now)` moves the live target — used by the calendar snap.
Rules:
1. `new_target <= now` → ignored (no-op).
2. `total_seconds` only ever **grows**:
   `total_seconds = max(total_seconds, new_target - started)`.
   It never shrinks. The stroke fraction and pulse curves are measured against
   `total_seconds`; shrinking it would make the ring jump *backwards*. Pulling
   the target *in* simply makes the ring drain faster — correct and smooth.
3. `SessionKind`, colour and event metadata may be updated alongside.

This is invariant #8 in [`architecture.md`](architecture.md). It is the single
subtlest rule in the domain — get it wrong and calendar snaps look broken.

### Per-tick computation (the heart of `tick`)
```
remaining       = max(0, target - now)            # seconds
target_fraction = remaining / total_seconds
display_fraction= lerp(display_fraction, target_fraction, dt, 9.0)
color           = stroke_color_for_fraction(display_fraction, cfg.red_zone_fraction, base)
pulse_phase    += dt * 0.85
frame = RenderFrame(
    fraction      = display_fraction,
    label         = format_duration(remaining) + calendar suffix if any,
    color         = color,
    pulse_opacity = pulse_opacity(remaining, cfg),
    pulse_spread  = pulse_spread(remaining, cfg),
    pulse_phase   = pulse_phase,
    blur          = blur_intensity(remaining, cfg),
)
```
`dt` is wall-clock seconds since the previous tick, floored at the frame
interval so a stalled run loop cannot produce a `dt` of 0 (which would freeze
the smoother) — see [`edge-cases.md`](edge-cases.md) #12.

---

## 8. What is intentionally *not* in the domain

So the boundary stays sharp:

- **Drawing.** The domain says `pulse_spread = 0.6`; turning that into stacked
  `NSBezierPath` fills is the overlay adapter's job.
- **The clock.** `tick` receives `now`. The domain never calls `datetime.now()`.
- **The frame timer.** ~60 Hz ticking is a `FrameScheduler` port.
- **Process lists.** The domain *plans* block-end from name lists; *getting*
  the lists and *executing* actions is an adapter.
- **Printing.** User-facing text goes through the `Logger` port.
