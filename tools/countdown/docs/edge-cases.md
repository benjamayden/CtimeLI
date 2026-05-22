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
Watch mode set `O_NONBLOCK` on file descriptor `0` to poll stdin and **never
cleared it**. That flag belongs to the open file description *shared with the
parent shell* — after the watcher exited, the user's terminal could start
throwing `BlockingIOError` on reads. A genuine, user-visible bug. **Fix**: the
`InputSource` port mandates `close()`, which restores the original flags; the
runner calls it in a `finally`.

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
The macOS adapters — `overlay.py`, `hud.py`, `stop_overlay.py`, `shaker.py`,
`app_control.py`, `block_executor.py`, `calendar.py`, `runloop.py` — call
PyObjC / EventKit / Accessibility / AppleScript and **cannot be exercised on
CI** (no Mac, no display). They are ported carefully and structurally
1:1 with the original, but treat them as **unverified until run on a Mac**. The
pure domain *is* verified — that is the whole point of the split. First Mac
run: follow [`development.md`](development.md) §"Manual macOS checklist".

---

## Repository hygiene

### #24 — `__pycache__` committed · Fixed
`tools/countdown/__pycache__/*.pyc` was tracked in git. **Fix**: `__pycache__/`
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

### #29 — `_finished_calendar_events` grows unbounded · Open
The watcher remembers every fired calendar event id in a set so it does not
re-trigger the same event; an id is only discarded once that event's start time
passes. Across a multi-day watch session the set grows slowly. Harmless in
practice (ids are small, sessions are hours not weeks) but unbounded. **Open**:
a port could cap it or evict by age. Low priority.
