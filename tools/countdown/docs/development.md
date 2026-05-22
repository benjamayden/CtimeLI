# Development guide

How to test, review, and extend the codebase without regressing it. Written for
both human and agent contributors.

---

## 1. Project setup

```sh
cd tools/countdown
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt          # PyObjC — macOS only
.venv/bin/pip install -e ".[dev]"                  # editable install + pytest
```

`requirements.txt` is the macOS runtime (PyObjC frameworks). The **domain and
tests need none of it** — pure-Python, runs on any OS. CI runs on Linux and
exercises everything except the macOS adapters.

Run the app via the bootstrap scripts (they create the venv on first use):

```sh
./run 15            ./run watch            ./shake --app-timing
```

Tune wiggle feel in `.env` (`SHAKE_*`); use `./shake --app-timing` to preview
before a long watch session. See [`configuration.md`](configuration.md) §"Window
wiggle".

---

## 2. Testing strategy

The split exists to make testing tractable. Three tiers:

### Tier 1 — Domain (exhaustive, runs everywhere)
`domain/` is pure, so every function is a table-driven unit test. **Target:
100% line and branch coverage of `domain/`.** No mocks needed — just inputs and
expected outputs.

- `test_math.py` — `smoothstep` endpoints/midpoint; `lerp` frame-rate
  independence; `format_duration` across h/m/s and negatives.
- `test_curves.py` — `pulse_opacity` (before/at/after window; ramp clamp),
  `pulse_spread` (linear vs `ramp_power=3`), `shake_intensity` (the 3 s window).
- `test_colors.py` — `stroke_color_for_fraction` above/at/below `red_zone`.
- `test_shake.py` — `ShakeMotion`: zero rest, amplitude bound, `reset`.
- `test_timespec.py` — **every row of the parsing table in
  [`domain.md`](domain.md) §4**, including the ambiguous-hour and error cases.
- `test_calendar.py` — `calendar_block_target`, `hard_stop_target`, `is_work_wifi`.
- `test_calendar_fields.py` — URL/room parsing from EventKit text fields.
- `test_blockend.py` — `plan_block_end`: precedence, alias expansion, the
  two-pass running-vs-foreground rule, skip sets.
- `test_config.py` — `AppConfig.from_mapping` parsing and `merge` (unknown
  override keys rejected — #6).
- `test_session.py` — **the whole transition table** ([`domain.md`](domain.md)
  §7): `RUNNING→BLOCKING` vs `→DONE` on `block_on_end`, `finish()` parity with
  zero, retarget never shrinking `total_seconds`, terminal-state no-ops.

### Tier 2 — Application (fakes, runs everywhere)
`app/` is tested by injecting **fake adapters** (`tests/fakes.py` — one per
port, see [`ports.md`](ports.md) summary table). A `SessionRunner` test:

1. Build `SessionRunner` with `FakeClock`, `FakeScheduler`, `FakeOverlay`, …
2. Advance `FakeClock`, hand-drive frames via `FakeScheduler`.
3. Assert on what the fakes recorded — `FakeOverlay.frames`, `FakeLogger.lines`,
   `FakeBlockExecutor.executed`.

This catches orchestration bugs (does zero trigger the stop overlay? does
`CLEANUP` run the plan exactly once?) with **no Mac and no display**.
`test_session_runner.py` covers the SessionRunner lifecycle; `test_watch_runner.py`
covers quick-add input, quit, and calendar auto-start / dedup.

### Tier 3 — Manual macOS checklist (the unverified surface)
The macOS adapters cannot run on CI. Verify by hand on a Mac after any change
to `adapters/macos/`:

- [ ] `./run 1` — stroke draws on every display; shrinks; turns red near zero.
- [ ] Edge glow blooms in the last ~2 min and deepens.
- [ ] Last 3 s: the frontmost window wiggles, then snaps back exactly.
- [ ] `./run 1 --block-on-end` — stop overlay covers all displays; ignores
      input for ~0.6 s; click/Return/Escape dismisses; windows tidy per `.env`.
- [ ] `./run watch` — type `1`, get a timer; type `q`, clean exit; **the
      terminal still works afterward** (regression guard for #18).
- [ ] Calendar event within 10 min auto-starts a green session.
- [ ] Remote call event (Zoom URL, off work Wi-Fi) opens browser at zero with no stop overlay.
- [ ] Room-only event shows room on stop overlay when `BLOCK_ON_END=true`.
- [ ] Hard stop (`HARD_STOP_ENABLED`) shows orange stroke in watch mode.
- [ ] Revoke Accessibility / Calendar permission → one warning, app still runs.

### Running tests
```sh
.venv/bin/pytest                       # all tiers 1+2
.venv/bin/pytest --cov=countdown/domain --cov-report=term-missing
```

---

## 3. Guard scripts (the build gates)

These run in CI and locally before a commit. A failure is a hard stop.

```sh
# Gate 1 — the dependency rule. domain/ and app/ must not import the platform
# or any adapter. Matches import lines only, so prose may mention "adapters".
grep -REn '^[[:space:]]*(import|from)[[:space:]].*(AppKit|objc|Cocoa|EventKit|ApplicationServices|adapters)' \
     countdown/domain countdown/app && echo "LAYERING VIOLATION" && exit 1

# Gate 2 — no bare user output outside adapters. Domain/app log via the port.
grep -REn '\bprint\(' countdown/domain countdown/app && echo "USE THE LOGGER" && exit 1

# Gate 3 — tests pass.
.venv/bin/pytest -q
```

> Gate 1 is the single most important check in the repo. It is what keeps the
> app portable. If it fails, you have leaked a platform dependency inward — move
> the code behind a port, do not suppress the grep.

---

## 4. Symbol migration map

Where every symbol from the old monolith now lives. Use this to navigate from
old code or old notes.

| Old location | Symbol | New home |
|--------------|--------|----------|
| `countdown.py` | `_smoothstep`, `_lerp`, `format_duration` | `domain/math.py` |
| `config.py` | `_smoothstep` (dup), `pulse_opacity`, `pulse_spread` | `domain/math.py`, `domain/curves.py` |
| `config.py` | `shake_intensity` | `domain/curves.py` |
| `config.py` | `pulse_intensity` | *deleted (#8)* |
| `countdown.py` | `STROKE_BLUE`, `STROKE_RED`, `_stroke_color_for_fraction` | `domain/colors.py` |
| `input_parse.py` | `parse_target_time`, `parse_quick_input` | `domain/timespec.py` |
| `calendar_monitor.py` | `CalendarEvent` | `domain/calendar.py` |
| `countdown.py` | `calendar_block_target`, `calendar_stroke_base` | `domain/calendar.py` |
| `countdown.py` | `_action_for_process`, alias tables, `_expand_block_end_names` | `domain/blockend.py` |
| `countdown.py` | `apply_block_end_actions` (planning half) | `domain/blockend.py::plan_block_end` |
| `countdown.py` | `apply_block_end_actions` (execution half) | `adapters/macos/block_executor.py` |
| `config.py` | `AppConfig`, `merge_cli` → `merge`, env parsers | `domain/config.py` *(pure value object)* |
| `config.py` | `load_dotenv` | `adapters/system/dotenv.py` *(no env mutation, #5)* |
| `countdown.py` | `CountdownApp` (lifecycle/state) | `domain/session.py` + `app/session_runner.py` |
| `countdown.py` | `Watcher` | `app/watch_runner.py` |
| `countdown.py` | `FocusShaker` | `adapters/macos/shaker.py` |
| `countdown.py` | `CountdownWindow`, `CountdownView`, `_draw_*` | `adapters/macos/overlay.py` |
| `countdown.py` | `CountdownHUDWindow`, `FinishControl` | `adapters/macos/hud.py` |
| `countdown.py` | `StopBlockWindow/View`, `_StopModalController` | `adapters/macos/stop_overlay.py` |
| `countdown.py` | `_pump_run_loop` | `adapters/macos/runloop.py` (`_TimerBridge` deleted, #11) |
| `countdown.py` | `_frontmost_pid`, `_activate_pid`, `_running_app_names`, … | `adapters/macos/app_control.py` |
| `calendar_monitor.py` | `CalendarMonitor` | `adapters/macos/calendar.py` |
| `countdown.py` | `_enable_stdin_nonblocking`, `_read_stdin_chunk` | `adapters/system/stdin_source.py` *(+restore, #18)* |
| `countdown.py` | `main`, `_main_countdown`, `_main_watch`, arg parsing | `cli.py` |
| `shake_test.py` | `ShakeTester` | *deleted; file renamed `shake_tune.py`, now drives `adapters/macos/shaker.py` + `domain/shake.py` (#10)* |

---

## 5. Code review checklist

Run this against any change before approving it.

### SOLID
- **S — Single Responsibility.** Does the module have one reason to change? A
  file that imports both `re` and `AppKit` is almost certainly two modules.
- **O — Open/Closed.** A new session kind / block action / input format should
  be a new *value* (enum member, table row), not a new `if` in an existing
  function. If you are editing a `match`/`if-elif` chain to add a case, ask
  whether a registry/strategy belongs there.
- **L — Liskov.** Every fake must honour its port's contract — same return
  types, same degradation behaviour. A fake that "can't fail" where the real
  adapter can hides bugs.
- **I — Interface Segregation.** Ports stay narrow. If an adapter implements a
  port but leaves half its methods as `pass`, the port is too wide — split it.
- **D — Dependency Inversion.** `app/` and `domain/` depend on `ports.py`, never
  on a concrete adapter. The only `import ... adapters` lines are in
  `composition.py`.

### DRY
- No formula appears twice. Curves, colours, parsing live once in `domain/`.
- No copy-pasted block > ~10 lines. (The retarget block, #14, was the warning.)
- A constant with meaning has a name (`FRAME_INTERVAL`, `_STOP_DISMISS_DELAY`),
  not a literal sprinkled around.

### Layering
- Gate 1 passes — no platform import in `domain/`/`app/`.
- New external dependency ⇒ new Port + adapter, not a direct call.
- Domain functions take data (incl. `now`), return data. No I/O, no clock.

### Tests
- New domain logic ⇒ new table-driven test, including the edge rows.
- New orchestration ⇒ a `*_runner` test with fakes.
- New macOS adapter behaviour ⇒ a line added to the manual checklist (§2).

---

## 6. Code-smell catalogue

The specific smells this codebase had, so they are recognised if they
re-appear. Each links to its [`edge-cases.md`](edge-cases.md) entry.

| Smell | Looks like | Cited |
|-------|-----------|-------|
| **Duplicated logic** | The same helper in two files. | #2, #3, #10, #11, #14 |
| **God object** | One class touching CLI, UI, FFI, state. | #1, #17 |
| **Implicit state** | Behaviour gated on N booleans instead of an enum. | #15 |
| **Feature envy / leaky encapsulation** | Class A reads/writes `B._private`. | #13 |
| **Hidden global side effect** | A "load" function mutating `os.environ`. | #5 |
| **Dead code / config** | Fields parsed but never read; deprecated aliases. | #7, #8 |
| **Lying signature** | A parameter the body ignores (`_ = total_sec`). | #9 |
| **Mixed responsibilities** | One function plans + does I/O + prints. | #22 |
| **Untestable purity loss** | A "pure" calc reaching for `datetime.now()`. | #4 |
| **Stringly-typed magic** | Process-name matching with scattered literals. | (blockend) |
| **Swallowed errors** | Bare `except Exception: pass`. | #23 |
| **Unmanaged resource** | A flag/fd set and never restored. | #18 |
| **Stale docs** | A `CLAUDE.md` describing a different project. | #27 |

**The fix is almost always the same**: name the concern, give it a home (a
domain function, or a port + adapter), inject it, test it.

---

## 7. How to add things

**A new config field** — add to `AppConfig`; add an env parser line; add a CLI
flag if user-facing; document it in [`configuration.md`](configuration.md) and
`.env.example`. Defaults make old `.env` files keep working.

**A new visual** — add a field to `RenderFrame`; compute it in `Session.tick`
from a new `domain/curves.py` function (unit-tested); render it in
`adapters/macos/overlay.py`. The overlay never gains logic — only drawing.

**A new session kind** — add a `SessionKind` value; give it a stroke colour;
attach any metadata to the session. The state machine and frame loop do **not**
change — that is the Open/Closed payoff. See [`features.md`](features.md)
§"Future session kinds".

**A new external dependency** — define a Port in `ports.py` (narrow!), write the
adapter under `adapters/`, add a fake to `tests/fakes.py`, construct it in
`composition.py`. Never call the dependency from `app/` directly.
