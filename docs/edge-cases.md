# Edge cases, bugs, and guards

This is the institutional memory. It records every bug, smell, and trap found
while turning the 1864-line monolith into the layered app — what it was, why it
mattered, and how it is now handled. **Read this before "simplifying"
anything**: several guards look pointless until you know the failure they
prevent.

Each entry has a **Status**:

- **Fixed** — the refactor removed the root cause.
- **Guarded** — the hazard is intrinsic; code defends against it. Keep the guard.
- **By design** — surprising but intentional; do not "fix" it.
- **Open** — known, not yet addressed; safe to pick up.

Numbers are stable IDs — other docs cite them (e.g. "see edge-cases #12").

---

## Structure & DRY

### #1 — The monolith · Fixed
`countdown.py` was 1864 lines: CLI, Cocoa drawing, Accessibility FFI, AppleScript
subprocesses, timer maths, a calendar poller and an implicit state machine in
one file. Untestable, unportable. **Fix**: the five-layer package in
[`architecture.md`](architecture.md).

### #2 — `_smoothstep` duplicated · Fixed
Defined identically in `countdown.py` and `config.py`. Two definitions drift.
**Fix**: one `domain/math.py::smoothstep`; every caller imports it.

### #3 — `_lerp` duplicated · Fixed
Defined in `countdown.py` and again in `shake_test.py`. **Fix**: one
`domain/math.py::lerp`.

### #8 — `pulse_intensity` dead alias · Fixed
`config.py` kept `pulse_intensity` as a "deprecated alias" that just called
`pulse_spread`. Dead code invites accidental use. **Fix**: deleted; callers use
`pulse_spread`.

### #10 — Shake logic duplicated in the tuning harness · Fixed
The old `shake_test.py`'s `ShakeTester` was a ~90% copy of `FocusShaker` — the
same AX window-move code maintained twice. **Fix**: the AX code lives once in
`adapters/macos/shaker.py` and the wiggle maths once in `domain/shake.py`. The
harness was renamed `shake_tune.py` (its `*_test.py` name wrongly matched
pytest's collector) and is now a thin script driving the real `WindowShaker`
adapter and `ShakeMotion`.

### #11 — `_TimerBridge` defined twice · Fixed
The PyObjC `NSTimer` target class existed in both `countdown.py` and
`shake_test.py`. **Fix**: deleted entirely. The runner owns the frame loop and
drives ticks itself; `MacScheduler` only pumps the run loop, so no `NSTimer`
(and no bridge class) is needed.

### #14 — Retarget block copy-pasted · Fixed
`Watcher._poll_calendar` and `Watcher._sync_calendar_to_nearest` contained the
*same* ~15-line "is there a sooner event? then retarget" block. A fix to one
would miss the other. **Fix**: one private method on `WatchRunner`.

### #22 — `apply_block_end_actions` did three jobs · Fixed
One ~60-line function decided actions, ran AppleScript, *and* printed a summary
— three reasons to change, none testable in isolation. **Fix**: pure
`domain/blockend.py::plan_block_end` (decide) + `BlockEndExecutor` port
(execute) + the app layer (summarise). See [`domain.md`](domain.md) §6.

---

## Encapsulation & design

### #13 — `Watcher` reached into `CountdownApp` privates · Fixed
The watcher read and wrote `countdown._blocked`, `._done`, `._interrupted`, and
even `countdown.windows[i]._view.stroke_base`. Any rename of a "private" broke a
distant file silently. **Fix**: `Session` exposes a real API — `state`,
`retarget()`, `request_interrupt()`, `set_base_color()` — and the runner uses
only that.

### #15 — Implicit 5-boolean state machine · Fixed
Session lifecycle was encoded in `_done`, `_interrupted`, `_blocked`,
`_stop_modal_active`, `_setup_complete`. 2⁵ = 32 nominal combinations, only ~6
legal; illegal ones were reachable. **Fix**: one explicit `SessionState` enum
with a documented transition table ([`domain.md`](domain.md) §7).

### #16 — User output via bare `print()` · Fixed
~40 `print(...)` calls, some to `stdout`, some to `stderr`, ad hoc. Output could
not be asserted in tests or redirected. **Fix**: the `Logger` port; adapters
choose the stream.

### #17 — `CountdownApp` had no dependency injection · Fixed
`__init__` took 11 parameters and *constructed its own* `FocusShaker` — a hard
dependency on macOS Accessibility baked into the controller, so the controller
could not be unit-tested. **Fix**: `SessionRunner` receives every port by
injection from the composition root.

### #20 — SIGINT handler did real work · Guarded
`Watcher._handle_sigint` mutated `self.countdown._interrupted` and `._done` from
inside the signal handler — re-entrancy waiting to happen (a signal can land
mid-mutation of those very fields). **Fix/Guard**: the `SignalListener` handler
only *latches a flag*; the app polls `interrupted()` between frames and drives
the state machine on the main thread. Never put logic in the handler.

---

## Hidden bugs

### #4 — Time parsers called the clock internally · Fixed
`parse_target_time` / `parse_quick_input` called `datetime.now()` inside
themselves, so the same input gave different results at different wall-clock
times and could not be unit-tested deterministically. **Fix**: `now` is an
explicit parameter ([`domain.md`](domain.md) §4). The composition layer passes
`Clock.now()`.

### #5 — `load_dotenv` mutated global `os.environ` · Fixed
It wrote `.env` values into `os.environ`, and only for keys *not already
present* — so a second call was a silent no-op and tests could not isolate
config. A spooky-action-at-a-distance global write. **Fix**: the `EnvSource`
adapter returns a plain mapping; `AppConfig` reads from it. `os.environ` is
never written. See [`ports.md`](ports.md) §`EnvSource`.

### #6 — `merge_cli(**overrides)` swallowed typos · Fixed
`merge_cli` accepted arbitrary `**kwargs` and applied any whose value was not
`None`. A misspelled key (`stoke_width=…`) was silently dropped — the override
just "didn't work", with no error. **Fix**: the merge validates every key
against `AppConfig`'s declared fields and raises on an unknown one.

### #12 — Zero `dt` freezes the smoother · Guarded
The per-frame delta drives `lerp`-based smoothing. If two ticks land in the same
instant (a stalled or coalesced run loop), `dt = 0` ⇒ `lerp` alpha `= 0` ⇒ the
stroke and wiggle freeze. **Guard**: `dt` is floored at `FRAME_INTERVAL`
(`1/60 s`) before it reaches any smoother. Keep this floor.

### #18 — `O_NONBLOCK` left on stdin · Fixed
Watch mode originally set `O_NONBLOCK` on file descriptor `0` to poll stdin and
**never cleared it**. That flag belongs to the open file description *shared with
the parent shell* — after the watcher exited, the user's terminal could start
throwing `BlockingIOError` on reads. **Fix**: the `InputSource` port mandates
`close()`, which restores the original flags; the runner calls it in a `finally`.
Watch mode now spawns a detached subprocess and uses `NullInputSource` in the
child, so stdin EOF no longer ends the watcher (see #36).

### #36 — Watch mode tied to terminal stdin · Fixed
The original watcher quit on stdin EOF, so closing the launch terminal killed
watch mode. It also relied on typed quick-add. **Fix**: watch launches a detached
subprocess (`spawn_detached_watch`); the parent prints a status line and exits;
the child uses the menu bar (`WatchMenuBar` port) and `NullInputSource`.
Calendar/hard-stop trumping cannot be disabled without Quit.

### #37 — `fork()` after PyObjC aborts the child · Fixed
An early implementation used `os.fork()` to background watch mode. After the
launcher imports AppKit/PyObjC, macOS aborts the fork child with
`* multi-threaded process forked *`. **Fix**: spawn a fresh
`python -m ctimeli watch` subprocess with `start_new_session=True` instead of
forking the already-initialized interpreter.

### #38 — Status-bar menu clicks ignored · Fixed
The first menu-bar adapter attached an `NSMenu` via `setMenu_` with a custom
`NSMenuItem` view. Clicks did nothing because the watch loop never pumped
`NSModalPanelRunLoopMode` (required for menus/alerts) and custom menu views are
unreliable on status items. **Fix**: manual `popUpMenuPositioningItem:` on
button click, standard menu items, `NSAlert` for minutes input, and pump modal
panel mode in `runloop.py`.

### #39 — Watch child crashed before showing the icon · Fixed
`NSStatusBarButton` has no `setSendActionOn_` in PyObjC — calling it raised
`AttributeError` in `show()`, killing the detached child while stderr was
`/dev/null`. **Fix**: drop that call; always show a visible `⏱` title; set
accessory activation policy before creating the item; log child output to
`~/.cache/ctimeli/watch.log`.

### #40 — `BrokenPipeError` in detached watch on calendar warn · Fixed
The detached child logged calendar-denial warnings to stderr; when the spawn
pipe closed, `StderrLogger.warn` raised `BrokenPipeError` and killed watch.
**Fix**: ignore `SIGPIPE` in the watch child, swallow broken-pipe writes in
`StderrLogger`, and redirect spawn stdout/stderr via a dedicated fd passed to
`Popen`.

### #41 — Status item never appeared despite “Watcher ready” · Fixed
Watch called `_init_appkit()` → `finishLaunching()` before setting an
`NSApplication` delegate, then created the `NSStatusItem` outside
`applicationDidFinishLaunching`. Cocoa accepts the setup but the item never
draws. Repeated `./run watch` also stacked multiple background children.
**Fix**: install the status item from an app delegate in
`applicationDidFinishLaunching_` (with a direct fallback), skip early
`finishLaunching` on the watch path, call `setVisible_(True)`, show the text
label **CtimeLI**, and guard with `WatchInstanceLock` so only one watch child
runs.

### #42 — Status-bar icon visible but menu clicks ignored · Fixed
After #41 the icon drew, but clicks did nothing. Root causes (all required):
1. Manual ``pump_run_loop`` / while-loop could not deliver status-bar events —
   watch must run on ``PyObjCTools.AppHelper.runEventLoop`` with ticks via
   ``callLater``.
2. ``_update_menu_bar`` called ``set_status`` / ``set_idle`` every 100 ms even
   when unchanged, repeatedly mutating ``NSStatusBarButton`` and breaking menu
   tracking — only update on change; skip bar refresh while the menu is open.
3. Wrong PyObjC constant ``NSStatusItemSquareLength`` (use
   ``NSSquareStatusItemLength``); attach menu via ``NSStatusItem.setMenu_``;
   icon-only idle state (timer SF Symbol, no title text).

### #21 — Synchronous quit can stall the loop · Guarded
`BlockEndExecutor` waits up to ~1 s (polling) for an app to actually terminate
before falling back to hide. That blocks the run loop. **Guard**: it only runs
once, in `CLEANUP`, after rendering has stopped — never on the per-frame path.
Do not move app-termination onto a live frame.

### #23 — Naked `except Exception` in mouse lookup · Guarded
`_mouse_location_cocoa` wraps two PyObjC calls in bare `except Exception`. Broad,
but deliberate: mouse position is best-effort (used only to hit-test the Finish
button) and a failure must degrade to "no click this frame", never crash the
session. **Guard kept, but narrowed**: it catches and the adapter logs at debug
level so a real regression is still discoverable.

---

## Platform pitfalls (macOS)

### #7 — Dead legacy config fields · Fixed
`shake_before_mins`, `shake_start_fraction`, `shake_nudge_seconds`,
`shake_nudge_level`, `shake_stop_before_mins` were parsed into `AppConfig` but
never read — the timing model had moved to the pulse/wiggle curves. Dead config
misleads. **Fix**: removed. Unknown env keys are ignored, so old `.env` files
still load.

### #9 — `shake_intensity`'s phantom parameter · Fixed
Signature was `shake_intensity(remaining, total_sec, cfg)`; the body opened with
`_ = total_sec`. A parameter every caller had to supply and the function
ignored. **Fix**: dropped — `shake_intensity(remaining, cfg)`.

### #19 — `NSGradient` crashes on Python 3.14 · Guarded
The edge glow would naturally be an `NSGradient`. Under PyObjC on Python 3.14 it
crashes the process. **Guard**: the glow is drawn as **seven stacked
translucent rectangle fills** with a manual fade (`_draw_soft_gradient_strip`).
It is intentionally not a "real" gradient. Do not "optimise" it back to
`NSGradient` without re-testing on the target Python.

### #28 — Ambiguous clock hours · By design
`12:00` parses to *the nearest of 00:00 and 12:00*; `0:30` to *the nearest of
00:30 and 12:30* — because an hour ≤ 12 with no meridiem is genuinely ambiguous
and the parser builds both candidates and picks the soonest
([`domain.md`](domain.md) §4). This is intended behaviour for a "quick timer"
tool: you almost always mean the *next* one. Use `am`/`pm` or 24-hour form to be
explicit. Documented, deliberately not "fixed".

### Unverified surface
The macOS adapters — `overlay.py`, `hud.py`, `blur.py`, `stop_overlay.py`,
`app_control.py`, `workspace_tidy.py`, `keyboard.py`, `url_opener.py`,
`calendar.py`, `runloop.py` — call PyObjC / EventKit / Accessibility / CGEvent
and **cannot be exercised on CI** (no Mac, no display). They are ported
carefully and structurally 1:1 with the original, but treat them as
**unverified until run on a Mac**. The pure domain *is* verified — that is the
whole point of the split. First Mac run: follow
[`development.md`](development.md) §"Manual macOS checklist".

---

## Repository hygiene

### #24 — `__pycache__` committed · Fixed
`__pycache__/*.pyc` was tracked in git. **Fix**: `__pycache__/`
added to `.gitignore`; the tracked `.pyc` files removed.

### #25 — `.DS_Store` committed · Fixed
A macOS Finder `.DS_Store` was tracked at the repo root. **Fix**: gitignored and
removed.

### #26 — Missing `.env.example` · Fixed
The `run` script's docstring and the original code referenced
`cp .env.example .env`, but no such file existed. **Fix**: a documented
`.env.example` ships with every key, its default, and a comment.

### #27 — Stale `CLAUDE.md` · Fixed
The repo-root `CLAUDE.md` described a *Rust* "nebulaos" workspace
(`crates/nebulaos-core`, Whisper, Ollama, …) that exists only in old git
history — nothing to do with the countdown app actually in the tree. An agent
picking up cold would be badly misled. **Fix**: `CLAUDE.md` rewritten to
describe this project and point at `docs/`.

### #30 — `foreground_apps()` used System Events AppleScript · Fixed

The original `foreground_apps()` fired `tell application "System Events" to get
name of every process whose background only is false`. Two failure modes:

1. **Automation permission** — macOS prompts the first time; if denied or
   revoked, the call returns `[]` silently, so no windows get the default
   minimize action.
2. **`missing value` bundle ID** — when the refactored version tried to also
   fetch bundle identifiers inline (`bundle identifier of p & "|" & name of p`),
   processes without a bundle ID caused AppleScript to build a list instead of
   a string, corrupting the entire output.
3. **Stale `background only` flag** — an app like Calendar shows
   `background only = false` even when it has no open window, producing a plan
   entry that minimizes nothing.

**Fix**: replaced with `Quartz.CGWindowListCopyWindowInfo(
kCGWindowListOptionOnScreenOnly | kCGWindowListExcludeDesktopElements,
kCGNullWindowID)`. The window server returns exactly the PIDs that have
unminimized on-screen windows. No AppleScript, no Automation permission.
`kCGWindowListExcludeDesktopElements` drops Finder's desktop/wallpaper layer so
Finder only appears when it has a real folder window open. Bundle IDs come from
`NSWorkspace` as before.

---

### #31 — `MacStopOverlay` activation and cursor · Fixed

Three related issues in the stop-overlay show path:

1. **`NSApp.activate()` silently fails** — on macOS 14+ the no-argument form
   requires the app to already be active. When a countdown fires from behind
   another app, `activate()` does nothing; the overlay is on screen but not key;
   the local event monitor never fires; clicks do not dismiss the overlay.
   **Fix**: always use `activateIgnoringOtherApps_(True)` (deprecated but
   reliable from any frontmost context).

2. **No click fallback** — the event monitor fires only for events delivered to
   our key window. During the brief activation window the monitor can miss the
   first click. **Fix**: `_StopModalController.poll_button_state()` is called
   each frame from `dismissed()`; it uses `NSEvent.pressedMouseButtons() & 1`
   to detect press-then-release independently of event delivery.

3. **Cursor visible over black overlay** — `NSCursor` is not automatically
   hidden by a full-screen window. **Fix**: `show()` calls `NSCursor.hide()`;
   `hide()` calls `NSCursor.unhide()`. Both are balanced by macOS's internal
   hide counter so a stray `unhide()` on an already-shown cursor is a no-op.

---

### #34 — Finish button click missed on non-key HUD window · Fixed

`FinishControl.mouseDown_` is not reliably delivered when `CountdownHUDWindow`
cannot become the key window. The same issue as the stop-overlay click (#31).
**Fix**: `MacOverlay.finish_requested()` calls `poll_finish_click()` on each
visible HUD window every frame — checks `NSEvent.pressedMouseButtons() & 1`
and hit-tests the button screen rect. `mouseDown_` remains as the fast path.

---

### #32 — Screen frozen during block-end cleanup · Fixed

`_run_cleanup()` called `stop_overlay.hide()` (which orders the windows out)
and then immediately entered the synchronous `workspace_tidy.tidy_focused()` path
(AppleScript calls, ~1 s total). `window.close()` enqueues a draw event but the
run loop never pumped between the close and the AppleScript stall, so the black
overlay remained visually composited on screen until cleanup finished.

**Fix**: `scheduler.pump(0.05)` is called after both `hide()` calls and before
`workspace_tidy.tidy_focused()`. This gives AppKit one run-loop cycle to composite
the now-closed windows before the blocking I/O begins. Do not remove this pump.

---

### #35 — `activate_finder` fallback was unnecessary · Fixed

`_restore_focus` called `activate_finder()` (via `osascript`) as a fallback
after the block-end tidy. By that point all app windows are already
hidden/minimized by the keyboard-shortcut tidy, so macOS handles the empty
desktop state without any explicit focus assignment.
**Fix**: removed `activate_finder` entirely. `_restore_focus` now only
re-activates the pre-block app when it is in the skip set (e.g. the host
terminal); otherwise it does nothing.

---

### #33 — Calendar late-start silently dropped events · Fixed

`calendar_block_target` returned `None` whenever
`event_start - block_before_mins <= now`, even if the event itself had not
started. With the default 7-minute buffer, any event less than 7 minutes away
produced no countdown — exactly the worst case for a time-blind user.
**Fix**: when the buffer has passed but the event hasn't started, return
`event_start` instead of `None`. The countdown fires to the meeting start,
giving whatever time remains. `None` is now returned only once the event has
already started.

---

### #29 — `_finished_calendar_events` grows unbounded · Fixed
The watcher remembers every fired calendar event id so it does not re-trigger
the same event. The old `set[str]` only evicted an id when that exact event
surfaced as the nearest future event again — which never happens once the event
has started. IDs therefore accumulated for the life of the process.
**Fix**: changed to `dict[str, dt.datetime]` (event_id → event_start).
`_evict_stale_finished()` runs every calendar poll cycle (≈15 s) and removes
any entry whose `event_start` is now in the past, regardless of what the
calendar currently returns.

---

### #36 — Per-app AppleScript tidy was slow · Fixed

The old `BlockEndExecutor` spawned `osascript` and walked every window of every
foreground app via System Events Accessibility (`AXMinimized`), taking seconds
with many windows open.

**Fix**: replaced with `WorkspaceTidy` — two synthetic keyboard shortcuts
(Option+⌘+H Hide Others, then ⌘+M Minimize) posted via `CGEvent` after
activating the pre-block frontmost app. Requires Accessibility permission.
Per-app `BLOCK_END_*` lists were removed; watch mode still un-hides the host
terminal via `NSRunningApplication.unhide()` after Hide Others.

---

### #43 — Accessibility permission never prompted · Fixed

`MacWorkspaceTidy` only checked `AXIsProcessTrusted()` at tidy time and logged
a warning — macOS never showed the system dialog, so users had to discover
Accessibility manually.

**Fix**: `WorkspaceTidy.ensure_access(*, prompt=True)` calls
`AXIsProcessTrustedWithOptions` with `kAXTrustedCheckOptionPrompt`. If macOS
does not show the dialog (already denied), it opens the Accessibility pane in
System Settings. The **foreground launcher** invokes this before
`spawn_detached_watch` — a detached child often cannot surface the prompt.
`install.sh` and `ctimeli permissions` run the same interactive setup; first
watch launch waits for the user to toggle **Python** (``sys.executable``), not
Terminal.app. Watch mode and one-shot mode also call it at startup when relevant.

---

### #44 — Calendar Allow dialog never appears for ``python -m ctimeli`` · Fixed

EventKit's ``requestFullAccessToEventsWithCompletion_`` returned ``granted=False``
immediately (TCC status stayed ``NotDetermined``) because the Python framework
``Info.plist`` shipped without ``NSCalendarsFullAccessUsageDescription``. macOS
cannot show the Allow/Don't Allow sheet without that key — opening Calendars in
System Settings does not help (there is no ``+`` button; apps appear only after
the native dialog).

**Fix**: ``install.sh`` adds the usage description to the Python framework plist
(one-time ``sudo``). ``ensure_calendar_dialog_ready()`` checks before requesting.
Calendar setup uses the native dialog; Settings opens only when status is
``Denied``.

---

### #45 — Python aborts ``RegisterApplication`` from Cursor terminal · Fixed

``activate_for_system_prompt()`` called ``setActivationPolicy(Regular)``, which
triggers ``RegisterApplication`` + menu-bar setup. That **SIGABRT**s when Python
is spawned from Cursor's integrated terminal (``Responsible Process: Cursor``).

**Fix**: all CLI AppKit bootstrap uses ``ActivationPolicyAccessory`` only
(``appkit_init.ensure_appkit_initialized``). ``./run permissions`` from Cursor
reopens the flow in **Terminal.app** via a ``.command`` script
(``CTIMELI_PERMISSIONS_IN_TERMINAL=1`` prevents relaunch loops).

---

### #46 — Watch segfault after block-end teardown · Fixed

Under ``AppHelper.runEventLoop``, ``SessionRunner._teardown()`` called
``window.close()`` synchronously at the end of a tick with ``yield_loop=False``.
PyObjC on Python 3.14 **SIGSEGV** (~exit 139) on the next event-loop turn even
though the watch loop correctly returned to idle.

**Fix**: one-shot mode (``yield_loop=True``) keeps synchronous ``close()``;
watch mode defers teardown and uses ``orderOut`` only (no ``close()``) via
``AppHelper.callLater(0, …)``. Calendar access is cached after the first denial
so ``_update_menu_bar`` does not re-hit EventKit every frame.
