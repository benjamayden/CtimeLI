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

## 4. Screen blur

In the final stretch the desktop **blurs progressively** — a peripheral nudge
that does not move windows or cause motion sickness.

- Active for the last `pulse_before_secs` seconds (default `120`) — the same
  window as the edge glow.
- Intensity ramps `0 → 1` across that window, shaped by `pulse_ramp_power`
  (`1` = linear, `3` = late/cubic) via `blur_intensity()` in [`domain.md`](domain.md).
- Rendered as a full-screen frosted-glass layer **below** the stroke/glow and
  HUD, so the countdown ring stays visible as the desktop blurs.
- At zero the screen is fully obscured; if `block_on_end` is on, the blur
  **persists** under the semi-transparent stop overlay and clears on dismiss.
- Always click-through — never intercepts mouse events.

**Acceptance**: with >120 s remaining there is no blur; inside the window blur
deepens monotonically toward zero; at zero the desktop is unreadable; with
`block_on_end` on the blurred desktop remains visible through the stop overlay
until dismiss.

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

The tidy runs in two keyboard-shortcut steps on the app that was frontmost when
the block fired:

1. **Option+⌘+H** — hide every other app (Hide Others).
2. **⌘+M** — minimize the focused app's front window.

In watch mode the host terminal is automatically un-hidden after step 1 and is
never minimized if it was the focused app.

Requires **Accessibility** permission (System Settings → Privacy & Security →
Accessibility) so synthetic key events can be posted.

After tidying, focus returns to the host terminal when it is in the watch-mode
`extra_skip` set (see edge-cases #35).

**Acceptance**: dismiss is near-instant; other visible apps are hidden; the
focused app is minimized into the Dock; terminal prints
`Block end: hid other apps, minimized focused window.`

## 9. Watch mode

`./run watch` starts a long-lived background watcher with a **menu bar icon**
(top-right). The launcher prints a one-line status and returns; you may close the
terminal. Use the menu bar to start timers, add time, or quit.

- **Menu bar Start**: enter minutes in the field → **Start** → a manual timer
  (replaces any running one).
- **Menu bar Add**: while a **pure manual** session runs (no pending calendar or
  hard stop), **Add** extends the deadline by N minutes. Disabled during calendar
  or hard-stop sessions.
- **Quit watch mode**: the only way to stop the watcher and calendar/hard-stop
  polling. There is no in-session toggle to disable calendar integration.
- **Calendar auto-start**: if calendar integration is on at watch start, the
  watcher polls for the nearest accepted upcoming event and starts a timer
  automatically so the block fires `calendar_block_before_mins` (default `7`)
  *before* the event.
- **Calendar / hard-stop priority**: whenever an accepted calendar or hard-stop
  candidate exists, it **always beats** a self-set manual countdown — on Start,
  on Add, and on every poll. Manual timers only run when no candidate is pending.
- **Calendar snap**: while a scheduled session runs, if a **sooner** candidate
  appears the watcher retargets the live session (and recolours the stroke).
- Between sessions the menu bar icon stays visible; the process uses an
  accessory activation policy (no Dock icon).

**Acceptance**: menu bar Start/Add/Quit work; closing the terminal does not stop
watch; calendar and hard-stop trump manual Start; Add is rejected when a
candidate is pending; a sooner calendar event retargets a scheduled session
without restarting it; Quit removes the menu bar icon and ends the process.

## 10. Input formats

Accepted for one-shot CLI and menu bar Start (minutes only):

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
| Accessibility permission / `ApplicationServices` | Block-end tidy no-ops; one warning; countdown still runs. Run `./run permissions` — flip **Python** ON in System Settings. |
| `EventKit` / Calendar Full Access | Calendar auto-start disabled; one warning; manual menu Start still works. Run `./run permissions` — click **Allow** on the macOS dialog. |
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
