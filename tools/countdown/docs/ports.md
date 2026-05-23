# Ports — interface contracts

A **Port** is an interface the application depends on; an **Adapter** is a
concrete implementation. Ports live in `ports.py` (Python `Protocol`s); adapters
live in `adapters/`. The application layer is written entirely against Ports, so
it can be driven by real macOS adapters in production and by fakes in tests.

Each port below lists: its **purpose**, its **methods** with pre/post-conditions,
its **failure mode**, and the **macOS adapter** that implements it. When you
port to another framework, you re-implement the adapters — the Port contracts do
not change.

Design rules for Ports (apply when adding one):
- **Narrow.** Expose what the app needs, not what the SDK offers. `ScreenBlur`
  has `set_intensity`, not `NSVisualEffectView`.
- **Domain types only.** Port signatures use `datetime`, `RGB`, `RenderFrame`,
  `CalendarEvent` — never `NSWindow`, `EKEvent`, `AXUIElement`.
- **Total, not partial.** A port method either succeeds or degrades visibly
  (returns `False`/`None`, logs once). It does not raise platform exceptions
  into the app layer.
- **No callbacks into the domain.** Adapters surface events as data the app
  polls or as plain values; they do not call domain functions.

---

## `Clock`

**Purpose** — supply time so the domain and app never touch a real clock.

| Method | Contract |
|--------|----------|
| `now() -> datetime` | Current wall-clock local time. Used for targets, parsing, calendar maths. |
| `monotonic() -> float` | Seconds from an arbitrary epoch, never decreasing. Used for throttling (calendar poll, dismiss delay) where wall-clock jumps must not matter. |

**Why two clocks**: wall-clock can jump (NTP, DST, sleep); monotonic cannot.
Durations and throttles use `monotonic`; "what time is the meeting" uses `now`.

**Failure** — none; this port cannot fail.
**Adapter** — `system/clock.py::SystemClock` (`datetime.now()` /
`time.monotonic()`). **Fake** — `FakeClock` with manually advanced time; the
backbone of every domain/app test.

---

## `Logger`

**Purpose** — all user-facing text. Replaces the ~40 scattered `print(...)`
calls so output is testable and redirectable.

| Method | Contract |
|--------|----------|
| `info(msg)` | Normal status (`Countdown → 14:00 …`). |
| `warn(msg)` | Recoverable degradation (`Shake disabled: …`). |
| `error(msg)` | A real failure the user must see. |

**Failure** — none.
**Adapter** — `system/logger.py::StderrLogger` (info→stdout, warn/error→stderr,
always flushed). **Fake** — `RecordingLogger` that appends to a list for
assertions.

> **Smell fixed.** The original printed directly everywhere, mixing `stdout`
> and `stderr` ad hoc and making output impossible to assert on. See
> [`edge-cases.md`](edge-cases.md) #16.

---

## `FrameScheduler`

**Purpose** — yield to the host UI event loop so overlays repaint, without the
app knowing about `NSRunLoop`. The runner owns the frame loop and drives ticks
itself; this port only drains pending platform UI events between ticks.

| Method | Contract |
|--------|----------|
| `pump(seconds)` | Process pending UI events for up to `seconds`. The runner calls this once per frame so a cooperative loop yields to the GUI. |
| `stop()` | Release any run-loop resources. Idempotent. |

**Failure** — none; on a headless port `pump` is a `sleep`.
**Adapter** — `macos/runloop.py::MacScheduler` — `NSRunLoop.runMode:beforeDate:`
over the event-tracking and default modes. No `NSTimer` is needed — the runner
ticks (edge-cases #11). **Fake** — `FakeScheduler` whose `pump` is a no-op and
whose frames the test drives by hand.

---

## `CountdownOverlay`

**Purpose** — render a `RenderFrame` (the stroke + edge glow) on every display.

| Method | Contract |
|--------|----------|
| `show()` | Create one borderless, click-through, all-Spaces window per display, above normal windows. |
| `render(frame: RenderFrame)` | Draw `frame` on every display: stroke length = `frame.fraction` of the perimeter, colour `frame.color`, glow from `pulse_opacity/spread/phase`. |
| `finish_requested() -> bool` | `True` once the user has clicked the HUD Finish button (latched). |
| `hide()` | Order the windows out (used while the stop overlay is up). |
| `teardown()` | Close and release everything. Idempotent. |

There is deliberately **no `set_base_color`**: `RenderFrame.color` already
carries the final stroke colour (the red-zone blend and any calendar recolour
are applied in the domain), so a mid-session recolour simply flows through the
next `render`. This keeps `RenderFrame` the *whole* UI contract (invariant #6).

**Pre** — `render` only between `show` and `teardown`.
**Post** — `render` is pure output; it never blocks and never reads state back.
**Failure** — a display vanishing mid-session must not crash; skip it.
**Adapter** — `macos/overlay.py` (`CountdownWindow`/`CountdownView`) +
`macos/hud.py` (label + Finish button — the HUD is part of this port's surface).

---

## `StopOverlay`

**Purpose** — the full-screen block-on-end modal.

| Method | Contract |
|--------|----------|
| `show(lines)` | Cover **every** display with an opaque modal above the screen-saver window level, displaying `lines`. Start a dismiss-lockout timer. |
| `dismissed() -> bool` | `True` once the user clicked / pressed Return / Escape **and** the lockout (`_STOP_DISMISS_DELAY = 0.6 s`) has elapsed. |
| `hide()` | Remove the modal. Idempotent. |

**Pre** — `dismissed()` polled each frame after `show`.
**Why the lockout** — at zero the app yanks focus; an in-flight keystroke would
otherwise dismiss the modal in the same instant. See
[`edge-cases.md`](edge-cases.md) #7.
**Failure** — none expected.
**Adapter** — `macos/stop_overlay.py` (`StopBlockWindow`/`StopBlockView` +
controller). `lines` is data so future session kinds can supply their own copy
(room name, "remote meeting", …) without touching the adapter.

---

## `ScreenBlur`

**Purpose** — progressive full-screen frosted glass above the stroke/glow, below
the HUD and block modal.

| Method | Contract |
|--------|----------|
| `show()` | Create one borderless, click-through blur window per display. |
| `set_intensity(amount)` | Set blur strength `0..1` on every display. At `0` windows are hidden. |
| `hide()` | Order blur windows out. Idempotent. |
| `teardown()` | Close and release everything. Idempotent. |

**Lifecycle** — `show` at session start; `set_intensity` each RUNNING frame; at
block-on-end the runner sets `1.0` and **does not hide** blur while the stop
overlay is up; `hide` on cleanup dismiss; `teardown` at session end.

**Failure** — a display vanishing mid-session must not crash; skip it.
**Adapter** — `macos/blur.py` (`BlurWindow` + `NSVisualEffectView`).
**Fake** — `FakeScreenBlur`.

---

## `AppControl`

**Purpose** — query and steer running applications (focus, listing, activation
policy). Everything `NSWorkspace`-ish that is *not* block-end execution.

| Method | Contract |
|--------|----------|
| `frontmost_pid() -> int \| None` | PID of the frontmost app; `None` if it is our own Python process (so we never "restore focus" to ourselves). |
| `app_name_for_pid(pid) -> str \| None` | Localised name for a PID. |
| `activate_pid(pid) -> bool` | Bring that app to the front; `False` if it is gone. |
| `activate_finder()` | Fallback focus target after a tidy. |
| `running_app_names() -> list[str]` | Every *regular* GUI app (includes windowless ones). Feeds block-end pass 1. |
| `foreground_app_names() -> list[str]` | Apps with a visible foreground presence. Feeds block-end pass 2. |
| `set_activation_policy(policy)` | `accessory` (no Dock icon, used during a session) / `prohibited` (fully hidden, watcher idle) / `regular` (focusable, for the stop modal). |

**Failure** — list methods return `[]` on error, never raise.
**Adapter** — `macos/app_control.py` (`NSWorkspace`, `NSApp`, and
`Quartz.CGWindowListCopyWindowInfo` for the foreground-window list — no
Automation permission required).

---

## `WorkspaceTidy`

**Purpose** — hide other apps and minimize the focused window after block-on-end.

| Method | Contract |
|--------|----------|
| `tidy_focused(*, skip) -> None` | Post Option+⌘+H (Hide Others), un-hide any `skip` apps, then ⌘+M on the frontmost unless it matches `skip`. |

**Pre** — the caller has already activated the pre-block frontmost app.
**Post** — other apps are hidden; the focused app's front window is minimized
unless skipped.
**Failure** — without Accessibility permission, logs one warning and no-ops.
**Adapter** — `macos/workspace_tidy.py` (`CGEvent` keyboard synthesis +
`NSRunningApplication.unhide` for watch-mode terminal skip).

---

## `CalendarSource`

**Purpose** — supply the nearest upcoming accepted event.

| Method | Contract |
|--------|----------|
| `ensure_access() -> bool` | Acquire calendar read permission. Idempotent; caches the result. `False` if denied or EventKit is absent. |
| `nearest_event_within(minutes) -> CalendarEvent \| None` | The nearest **accepted** event starting in `(now, now+minutes]`, or `None`. Declined events excluded ([`domain.md`](domain.md) §5). |

**Pre** — `nearest_event_within` self-calls `ensure_access`; a caller need not.
**Failure** — no EventKit / denied permission ⇒ both return falsey, one warning
logged; the app runs without calendar features.
**Adapter** — `macos/calendar.py` (`EKEventStore`,
`predicateForEventsWithStartDate:endDate:calendars:`). Parses `call_url` and
`room` via `domain/calendar_fields.py`. **Fake** —
`FakeCalendar` returning a scripted list.

---

## `UrlOpener`

**Purpose** — open a meeting URL in the default browser at zero.

| Method | Contract |
|--------|----------|
| `open(url) -> bool` | Hand the URL to the workspace. Return `True` on success. |

**Adapter** — `macos/url_opener.py` (`NSWorkspace.openURL_`). **Fake** —
`FakeUrlOpener` recording opened URLs.

---

## `WifiSource`

**Purpose** — report the current Wi-Fi SSID for work-network gating.

| Method | Contract |
|--------|----------|
| `current_ssid() -> str \| None` | Connected SSID, or `None` if unavailable. |

**Adapter** — `system/wifi.py` (`networksetup -getairportnetwork`). **Fake** —
`FakeWifiSource` with a settable SSID.

---

## `InputSource`

**Purpose** — non-blocking line input for watch mode.

| Method | Contract |
|--------|----------|
| `poll_lines() -> list[str]` | Complete lines typed since the last call (may be empty). Never blocks. |
| `closed() -> bool` | `True` once stdin reaches EOF. |
| `close()` | Restore the terminal to blocking mode. **Must** run on shutdown. |

**Why `close()` matters** — the adapter sets `O_NONBLOCK` on fd 0; that flag is
shared with the parent shell and, if not cleared, can leave the user's terminal
misbehaving after exit. See [`edge-cases.md`](edge-cases.md) #18 — a real bug in
the original, now fixed by this port's contract.
**Adapter** — `system/stdin_source.py` (`fcntl` + `select`).

---

## `SignalListener`

**Purpose** — surface `Ctrl+C` as data, not as an exception mid-frame.

| Method | Contract |
|--------|----------|
| `install()` | Register the `SIGINT` handler. |
| `interrupted() -> bool` | `True` once `SIGINT` has fired (latched). |
| `restore()` | Reinstate the previous handler. |

**Why a port** — the handler must only *set a flag*; the app polls
`interrupted()` between frames and drives the state machine cleanly. Doing real
work inside a signal handler is the classic re-entrancy bug.
**Adapter** — `system/signals.py` (`signal.signal`).

---

## `EnvSource` (composition-time only)

**Purpose** — read configuration without a global side effect.

| Method | Contract |
|--------|----------|
| `values() -> Mapping[str, str]` | Merged view of process env over `.env`-file values. Pure read; **never mutates `os.environ`**. |

> **Smell fixed.** The original `load_dotenv` wrote into `os.environ` and only
> for keys "not already set", so a second call silently no-op'd and tests could
> not isolate config. The loader now returns a mapping and `AppConfig` reads
> from it. See [`edge-cases.md`](edge-cases.md) #5.

**Adapter** — `system/dotenv.py`. Used only by `composition.py`; not injected
into the app or domain.

---

## Port → adapter → fake summary

| Port | macOS adapter | Test fake |
|------|---------------|-----------|
| `Clock` | `SystemClock` | `FakeClock` |
| `Logger` | `StderrLogger` | `RecordingLogger` |
| `FrameScheduler` | `runloop.MacScheduler` | `FakeScheduler` |
| `CountdownOverlay` | `overlay.MacOverlay` (+ HUD) | `FakeOverlay` |
| `StopOverlay` | `stop_overlay.MacStopOverlay` | `FakeStopOverlay` |
| `ScreenBlur` | `blur.MacScreenBlur` | `FakeScreenBlur` |
| `AppControl` | `app_control.MacAppControl` | `FakeAppControl` |
| `WorkspaceTidy` | `workspace_tidy.MacWorkspaceTidy` | `FakeWorkspaceTidy` |
| `CalendarSource` | `calendar.EventKitCalendar` | `FakeCalendar` |
| `UrlOpener` | `url_opener.MacUrlOpener` | `FakeUrlOpener` |
| `WifiSource` | `wifi.SystemWifi` | `FakeWifiSource` |
| `InputSource` | `stdin_source.StdinSource` | `FakeInput` |
| `SignalListener` | `signals.SigintListener` | `FakeSignals` |
| `EnvSource` | `dotenv.DotEnvSource` | plain `dict` |
