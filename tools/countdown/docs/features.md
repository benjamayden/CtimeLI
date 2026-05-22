# Features

The product, described as observable behaviour. Each feature has an acceptance
criterion: a sentence that is either true or false of a correct
implementation. If you are rebuilding the app, these are your conformance
tests.

## 1. The screen-edge stroke

A thin coloured line is drawn around the perimeter of **every** display. Its
length encodes time remaining: a full perimeter at the start, shrinking
clockwise to nothing at zero.

- The line is **click-through** — it never intercepts mouse events.
- It floats above normal windows and joins all Spaces / full-screen apps.
- Drawn length follows the true fraction through an exponential smoother so it
  glides rather than steps (rate `DISPLAY_SMOOTH_RATE = 9.0` per second).

**Acceptance**: at `t` seconds remaining of a `T`-second session, the stroke
covers `t/T` of the screen perimeter (after smoothing settles), on each
attached display.

## 2. Red-zone colour shift

As the stroke gets short it changes colour from its base hue to red, warning
that time is nearly out.

- Triggered when the *fraction remaining* drops to `red_zone_fraction`
  (default `0.05` — the last 5%).
- The shift is a smoothstep interpolation, not a hard switch.
- Base colour depends on **session kind**: manual = blue, calendar = green.
  (Future kinds — see §10 — add their own.)

**Acceptance**: above 5% remaining the stroke is the base colour; at 0% it is
fully red; between, it is a smooth blend.

## 3. Edge glow (pulse)

In the final stretch a soft glow blooms inward from the screen edges — a
peripheral-vision nudge that does not demand focus.

- Active for the last `pulse_before_secs` seconds (default `120`).
- Two independent curves (full formulas in [`domain.md`](domain.md)):
  - **Opacity** ramps `0 → pulse_max_opacity` over the first
    `pulse_opacity_ramp_secs` (default `10`) of the window — it appears quickly.
  - **Spread** (how deep the glow reaches inward) grows across the *whole*
    window, shaped by `pulse_ramp_power` (`1` = linear, `3` = late/cubic).
- Rendered as stacked translucent fills, not a real gradient — see
  [`edge-cases.md`](edge-cases.md) for why (`NSGradient` crashes on Python 3.14).

**Acceptance**: with >120 s remaining there is no glow; inside the window the
glow is visible and deepens monotonically toward zero.

## 4. Frontmost-window wiggle

In the very last seconds the *frontmost application's window* physically
oscillates — a hard-to-ignore "wrap it up" signal.

- Active only for the final `shake_wiggle_seconds` (default `3`).
- Intensity ramps `0 → 1` via smoothstep across those seconds.
- Motion is a smoothed two-frequency sine on both axes; the window's original
  position is **always restored** when the wiggle ends or the session stops.
- Certain apps are **never** wiggled: the host terminal, editors used to launch
  it (Cursor, VS Code), the Python process itself, and system UI
  (Dock, WindowManager, …). See [`configuration.md`](configuration.md).
- Requires macOS Accessibility permission. Without it the feature disables
  itself with one warning and the rest of the app runs normally.
- Tune motion in `.env` (`SHAKE_*`); preview with `./shake --app-timing`. See
  [`configuration.md`](configuration.md) §"Window wiggle".

**Acceptance**: with >3 s left, no window moves; in the last 3 s the frontmost
window wiggles with rising amplitude; after zero (or on quit) it sits exactly
where it started. `./shake --app-timing` with a non-terminal window focused
should feel the same in the final `SHAKE_WIGGLE_SECONDS`.

## 5. The HUD

A small panel in the top-right corner of each display shows the remaining time
as `1h 02m 03s` / `12m 04s` / `9s`, plus a **Finish** button.

- The HUD *is* clickable (unlike the stroke). Clicking **Finish** ends the
  session early.
- For a calendar session the label also shows the event start: `12m 04s · 14:00`.

**Acceptance**: the label matches `format_duration(remaining)`; clicking Finish
transitions the session exactly as reaching zero would.

## 6. Finish early

Ends the running session before its target.

- Via the HUD **Finish** button, or `Ctrl+C`.
- If `block_on_end` is **off**: the session ends immediately (state → `DONE`).
- If `block_on_end` is **on**: it behaves like reaching zero — the stop overlay
  appears first (state → `BLOCKING`).

**Acceptance**: Finish honours `block_on_end` identically to a natural zero.

## 7. Block-on-end (the stop overlay)

When `block_on_end` is enabled, hitting zero does not just end the timer — it
**covers every screen** with an opaque overlay that says *"It's time to stop."*

- The overlay sits *above the screen-saver window level* so nothing buries it.
- It ignores input for the first `0.6 s` (`_STOP_DISMISS_DELAY`) so a stray
  keystroke in flight cannot dismiss it instantly.
- It is dismissed by a click anywhere, `Return`, or `Escape`.
- The stroke + HUD are hidden while the overlay is up.
- On dismiss, the **block-end tidy** runs (§8), then the session ends.

**Acceptance**: at zero with `block_on_end` on, all displays are covered; input
in the first 0.6 s is ignored; a click/Return/Escape after that dismisses it
and triggers the tidy.

## 8. Block-end window tidy

After the stop overlay is dismissed, the app tidies your workspace so you
actually leave it.

Each running GUI app is assigned **one** action:

| Action | Effect |
|--------|--------|
| `minimize` | Minimise the app's windows. |
| `hide` | Hide the app (`⌘H` equivalent). |
| `quit` | Terminate the app; if termination fails, fall back to hide. |
| `skip` | Leave the app untouched. |

Assignment precedence (first match wins):

1. App is in the system-skip set or `block_end_skip` → **skip**.
2. App is in `block_end_quit` → **quit**.
3. App is in `block_end_hide` → **hide**.
4. App is in `block_end_minimize` → **minimize**.
5. Otherwise → `block_end_default` (default `minimize`).

Notes:
- Explicit lists act on **every** running instance; the default acts on
  apps with a visible foreground presence.
- App names accept aliases — `chrome` resolves to *Google Chrome*. Full alias
  table in [`configuration.md`](configuration.md).
- Finder is never terminated (macOS forbids it) — it is hidden instead.
- After tidying, focus returns to the launching terminal (or Finder).

**Acceptance**: given a config and a set of running apps, each app receives
exactly the action the precedence table dictates; a one-line summary is
reported (`Block end: minimized 3 windows, quit 1 app.`).

## 9. Watch mode

`./run watch` starts a long-lived watcher instead of a single timer.

- **Quick-add**: type `15` + Enter → a 15-minute timer; type `14:00` → a timer
  to 2 pm; type `q` / `quit` / `exit` → leave. Starting a new timer replaces
  any running one.
- **Calendar auto-start**: if calendar integration is on, the watcher polls for
  the nearest accepted upcoming event and starts a timer automatically so the
  block fires `calendar_block_before_mins` (default `7`) *before* the event.
- **Calendar snap**: while a timer runs, if a sooner event appears the watcher
  *retargets* the live session to it (and recolours the stroke green).
- Between sessions the watcher hides itself and waits.

**Acceptance**: typed input and calendar events both produce sessions; a newer,
sooner calendar event retargets the running session without restarting it.

## 10. Input formats

Accepted everywhere a time is entered (CLI argument, `--at`, watch stdin):

| Input | Meaning |
|-------|---------|
| `15`, `90` (bare digits) | That many **minutes** from now. |
| `0.5`, `2.5` (decimal) | That many minutes from now (fractional). |
| `6:00`, `18:30`, `9:05:30` | The next future occurrence of that **clock time**. |
| `6:00pm`, `7am` | Clock time with explicit meridiem. |
| `--for-minutes 25` | Explicit minutes form (one-shot CLI only). |

Ambiguity rule: bare digits are *always* minutes, never an hour — `6` means six
minutes, not 6 o'clock. Full parser spec and corner cases in
[`domain.md`](domain.md) §"Time parsing".

## 11. Multi-monitor

Every overlay — stroke, HUD, stop modal — is created once per `NSScreen`. The
session drives them in lockstep from a single state.

**Acceptance**: with two displays attached, both show the stroke, both show a
HUD, and the stop overlay covers both.

## 12. Graceful degradation

The app runs even when optional pieces are missing — it never hard-crashes on a
permission gap:

| Missing | Behaviour |
|---------|-----------|
| Accessibility permission / `ApplicationServices` | Wiggle disabled; one warning; everything else runs. |
| `EventKit` / Calendar Full Access | Calendar auto-start disabled; one warning; manual + quick-add still work. |
| A display unplugged mid-session | Remaining displays keep rendering. |

---

## Session kinds beyond manual

The architecture treats "session kind" as an open enum — new kinds are *data*,
not new frame-loop branches.

### Hard stop (watch mode)

- **Trigger**: `HARD_STOP_ENABLED=true` and the current time is within
  `(hard_stop_time − warning_mins, hard_stop_time]`.
- **Stroke**: orange (`HARD_STOP_STROKE_*`).
- **HUD**: `12m 04s · hard stop 22:00`.
- **At zero**: normal block-on-end when `BLOCK_ON_END=true`; stop overlay shows
  *End of day.* / *Hard stop — time to wrap up.*
- **Priority**: nearest `block_at` wins — a calendar cleanup at 21:53 beats a
  hard stop at 22:00 if both are in window.

**Acceptance**: `./run watch` with `HARD_STOP_TIME` ~2 min ahead and
`HARD_STOP_WARNING_MINS=30` → orange stroke; block fires at the configured time.

### Calendar call links

- **Trigger**: calendar event with a meeting URL (`call_url`) and no physical
  `room`.
- **Off work Wi-Fi** (`WORK_WIFI_SSIDS`): at zero, opens the URL in the default
  browser and ends cleanly — **no** stop overlay, **no** window tidy, even when
  `BLOCK_ON_END=true` (so the meeting tab is not minimised).
- **On work Wi-Fi**: no browser open; block-on-end runs normally if enabled.

**Acceptance**: off-work Wi-Fi, Zoom URL event, `BLOCK_ON_END=true` → browser
opens, no full-screen overlay, Chrome stays foreground.

### Room overlay

- **Trigger**: calendar event with a non-URL `location` (e.g. *Room 4B*).
- **At zero**: normal block-on-end; stop overlay shows *Room: {room}* instead of
  the default copy. Browser is **not** opened.

**Acceptance**: location `"Room 3A"`, `BLOCK_ON_END=true` → overlay shows room,
tidy on dismiss as today.
