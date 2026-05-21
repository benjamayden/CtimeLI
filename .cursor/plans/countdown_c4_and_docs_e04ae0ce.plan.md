---
name: Countdown C4 and docs
overview: Create `tools/countdown/architecture.md` with C4 Mermaid diagrams (context → container → component), workflow sequences, and a companion documentation set that gives an agent everything needed to rebuild the app as a SOLID, DRY Python package — without performing the refactor yet.
todos:
  - id: create-architecture-md
    content: Write tools/countdown/architecture.md with C4 Context/Container/Component + sequence + state Mermaid diagrams
    status: pending
  - id: create-features-domain
    content: Write docs/features.md and docs/domain-model.md (session kinds, entities, invariants, future extensions)
    status: pending
  - id: create-config-workflows
    content: Write docs/config-reference.md (all AppConfig/env/CLI) and docs/workflows.md (edge cases + behavior tables)
    status: pending
  - id: create-interfaces-module-map
    content: Write docs/interfaces.md (target protocols) and docs/module-map.md (symbol → target module migration table)
    status: pending
  - id: create-ops-docs
    content: Write docs/macos-permissions.md, docs/testing-strategy.md, docs/migration-checklist.md (ordered refactor gates)
    status: pending
isProject: false
---

# Countdown app: C4 architecture + SOLID rebuild documentation plan

## What exists today

A macOS-only **screen-edge countdown timer** in [`tools/countdown/`](tools/countdown/). Invoked via [`tools/countdown/run`](tools/countdown/run) (venv bootstrap + `countdown.py`).

| File | Lines | Role |
|------|-------|------|
| [`countdown.py`](tools/countdown/countdown.py) | ~1621 | **Monolith**: CLI, UI (PyObjC), session loop, shake, block-end, watcher |
| [`config.py`](tools/countdown/config.py) | ~172 | `.env` loader + `AppConfig` + `shake_intensity()` |
| [`calendar_monitor.py`](tools/countdown/calendar_monitor.py) | ~181 | EventKit polling → `CalendarEvent` |
| [`input_parse.py`](tools/countdown/input_parse.py) | ~70 | Time/minute parsing for CLI + watch stdin |
| [`shake_test.py`](tools/countdown/shake_test.py) | ~267 | Standalone shake tuning harness (duplicates AX logic) |

**SOLID/DRY violations to document (not fix yet):**
- `_smoothstep` duplicated in `countdown.py` and `config.py`; `_lerp` duplicated in `countdown.py` and `shake_test.py`
- `FocusShaker` AX window-move logic duplicated in `shake_test.py`
- PyObjC view classes, AppleScript subprocesses, and session state machine all live in one file
- No protocols/interfaces — concrete macOS bindings are hard-wired
- `CountdownApp` owns UI creation, tick loop, stop modal, and block-end side effects
- Debug agent-logging hardcoded to a repo path inside production code

**Planned but not yet implemented** (from [`.cursor/plans/calendar_calls_hard_stop_f02c9444.plan.md`](.cursor/plans/calendar_calls_hard_stop_f02c9444.plan.md)): hard-stop sessions, WiFi SSID gating, calendar call URLs/rooms, dynamic stop-overlay copy. Documentation should include these as **future session kinds** so the target architecture accommodates them.

---

## Deliverable 1: `tools/countdown/architecture.md`

Single markdown file with the sections below. All diagrams use Mermaid (C4 + sequence + state).

### Level 1 — System Context

```mermaid
C4Context
  title Countdown — System Context

  Person(user, "User", "ADHD-focused worker running timed sessions from terminal")

  System(countdown, "Countdown App", "macOS screen-edge timer with shake nudge and optional block-on-end")

  System_Ext(calendar, "macOS Calendar", "EventKit — accepted upcoming events")
  System_Ext(accessibility, "macOS Accessibility", "AX APIs — move frontmost window")
  System_Ext(system_events, "System Events / NSWorkspace", "Hide, minimize, quit apps; activate terminal")
  System_Ext(screens, "NSScreen / NSWindow", "Multi-monitor borderless overlays")

  Rel(user, countdown, "Runs ./run 15, ./run 6:00, ./run watch; types quick timers; Ctrl+C")
  Rel(countdown, calendar, "Polls nearest accepted event; auto-start / retarget")
  Rel(countdown, accessibility, "Shake frontmost window during final minutes")
  Rel(countdown, system_events, "Block-end: minimize/hide/quit per .env rules")
  Rel(countdown, screens, "Stroke overlay + HUD + stop modal on all displays")
```

### Level 2 — Container Diagram

```mermaid
C4Container
  title Countdown — Containers (current layout)

  Person(user, "User", "Terminal operator")

  Container_Boundary(app, "Countdown Python App") {
    Container(cli, "CLI Entry", "Python argparse", "./run → main(); countdown vs watch subcommand")
    Container(config, "Config", "config.py", "AppConfig from .env + CLI merge")
    Container(input, "Input Parser", "input_parse.py", "Minutes, clock times, watch stdin")
    Container(watcher, "Watcher", "countdown.py Watcher", "Long-lived loop: stdin + calendar poll + session pump")
    Container(session, "Session Controller", "countdown.py CountdownApp", "Timer state, retarget, finish, block modal")
    Container(ui, "UI Layer", "PyObjC NSWindow/NSView", "Stroke, HUD, Finish, StopBlock modal")
    Container(shake, "Focus Shaker", "countdown.py FocusShaker", "AX window position oscillation")
    Container(block, "Block-End Actions", "countdown.py apply_block_end_actions", "AppleScript + NSWorkspace quit")
    Container(cal, "Calendar Monitor", "calendar_monitor.py", "EventKit store, nearest event")
  }

  System_Ext(eventkit, "EventKit", "EKEventStore")
  System_Ext(ax, "ApplicationServices AX", "AXUIElement window position")
  System_Ext(osa, "osascript", "System Events hide/minimize")
  System_Ext(ns, "AppKit / Cocoa", "NSRunLoop, NSTimer, NSScreen")

  Rel(user, cli, "argv, stdin (watch)")
  Rel(cli, config, "loads")
  Rel(cli, watcher, "watch mode")
  Rel(cli, session, "one-shot mode")
  Rel(watcher, input, "parse_quick_input")
  Rel(watcher, cal, "poll / auto-start")
  Rel(watcher, session, "creates, pumps pump_frame")
  Rel(session, ui, "setup, tick, stop modal")
  Rel(session, shake, "update each frame")
  Rel(session, block, "on modal dismiss")
  Rel(cal, eventkit, "eventsMatchingPredicate")
  Rel(shake, ax, "AXPosition read/write")
  Rel(block, osa, "hide/minimize")
  Rel(block, ns, "terminate apps")
  Rel(ui, ns, "draw stroke, run loop")
```

### Level 3 — Component Diagram (inside Session + UI)

```mermaid
C4Component
  title Countdown — Components (logical, mostly in countdown.py today)

  Container_Boundary(session, "Session Controller") {
    Component(countdown_app, "CountdownApp", "Orchestrator", "target, total_seconds, stroke_base, lifecycle")
    Component(timer_tick, "Tick Loop", "_on_tick / _tick", "remaining, display lerp, HUD label, shake dispatch")
    Component(retarget, "Retarget", "retarget()", "Calendar snap without resetting total_seconds down")
    Component(stop_flow, "Stop Modal Flow", "_enter_stop_modal → dismiss → block_end", "Block-on-end pipeline")
    Component(finish, "Finish Early", "finish_early()", "HUD Finish button → optional stop modal")
  }

  Container_Boundary(ui, "UI Layer") {
    Component(stroke_win, "CountdownWindow/View", "Per-screen stroke", "Perimeter draw, red-zone color lerp")
    Component(hud, "CountdownHUDWindow", "Timer label + Finish", "Click-through stroke; interactive HUD corner")
    Component(stop_ui, "StopBlockWindow/View", "Full-screen modal", "Dismiss: click, Return, Escape after delay")
    Component(runloop, "Run Loop Utils", "_pump_run_loop, _TimerBridge", "60fps NSTimer + manual pump in watch")
  }

  Container_Boundary(integrations, "macOS Integrations") {
    Component(focus_shaker, "FocusShaker", "AX shake", "frontmost window, restore on zero")
    Component(block_actions, "apply_block_end_actions", "Process resolver", "foreground scan → hide/minimize/quit")
    Component(host_reactivate, "_reactivate_host_app", "Watch mode", "Return focus to terminal after block")
  }

  Rel(countdown_app, timer_tick, "NSTimer drives")
  Rel(timer_tick, stroke_win, "setProgress_")
  Rel(timer_tick, hud, "setLabel_")
  Rel(timer_tick, focus_shaker, "update(remaining)")
  Rel(finish, stop_flow, "if block_on_end")
  Rel(stop_flow, stop_ui, "show/dismiss")
  Rel(stop_flow, block_actions, "after dismiss")
  Rel(stop_flow, host_reactivate, "watch_mode only")
  Rel(retarget, countdown_app, "updates target, event metadata")
```

### Workflow — One-shot manual countdown

```mermaid
sequenceDiagram
  participant User
  participant CLI as main/_main_countdown
  participant Config as AppConfig
  participant App as CountdownApp
  participant UI as Stroke+HUD
  participant Shake as FocusShaker

  User->>CLI: ./run 15
  CLI->>Config: from_env + merge_cli
  CLI->>App: CountdownApp(target, cfg)
  App->>UI: setup() — windows per NSScreen
  loop 60fps until target
    App->>App: _tick — remaining, display lerp
    App->>UI: setProgress_, setLabel_
    App->>Shake: update(remaining)
  end
  alt block_on_end
    App->>App: _enter_stop_modal
    User->>App: dismiss modal
    App->>App: apply_block_end_actions
  else no block
    App->>App: _done = True
  end
  App->>App: _teardown
```

### Workflow — Watch mode (calendar + stdin)

```mermaid
sequenceDiagram
  participant User
  participant Watcher
  participant Cal as CalendarMonitor
  participant App as CountdownApp
  participant Input as parse_quick_input

  User->>Watcher: ./run watch
  Watcher->>Cal: ensure_access
  Watcher->>Cal: nearest_event_within
  alt event in window
    Watcher->>App: start at calendar_block_target
  end
  loop until quit
    Watcher->>Watcher: _poll_stdin
    opt user types "20"
      Watcher->>Input: parse_quick_input
      Watcher->>App: _start_countdown_at (replaces running)
    end
    Watcher->>Watcher: _poll_calendar every N sec
    opt sooner calendar event
      Watcher->>App: retarget(block_at, calendar metadata)
    end
    Watcher->>App: pump_frame()
    opt session ended + block dismissed
      Watcher->>Watcher: _reactivate_host_app; countdown = None
    end
  end
```

### State machine — Session lifecycle

```mermaid
stateDiagram-v2
  [*] --> Idle: watch starts
  [*] --> Running: one-shot starts

  Idle --> Running: stdin timer OR calendar auto-start
  Running --> Running: retarget (calendar snap)
  Running --> StopModal: target reached AND block_on_end
  Running --> Done: target reached AND NOT block_on_end
  Running --> StopModal: Finish early AND block_on_end
  Running --> Done: Finish early AND NOT block_on_end
  Running --> Interrupted: Ctrl+C (one-shot) OR stop() (watch)

  StopModal --> TidyWindows: user dismisses
  TidyWindows --> Idle: watch_mode
  TidyWindows --> Done: one-shot

  Interrupted --> Idle: watch teardown
  Interrupted --> [*]: one-shot exit
  Done --> [*]
  Idle --> [*]: q / EOF
```

---

## Deliverable 2: Documentation set for SOLID/DRY rebuild

An agent rebuilding this app needs **spec + architecture + contracts + behavior tables**, not just diagrams. Create these files under `tools/countdown/docs/` (or flat in `tools/countdown/` — prefer `docs/` to keep root clean):

### Required documents

| Doc | Purpose | Key contents |
|-----|---------|--------------|
| **`architecture.md`** | C4 + state + container map | Diagrams above; link to all other docs |
| **`features.md`** | Feature inventory | Manual timer, watch mode, calendar auto-start/retarget, multi-monitor stroke, red-zone color, shake curve, block-on-end, finish early, per-app block rules; **future**: hard stop, call URL, room overlay, WiFi gate |
| **`workflows.md`** | Step-by-step behavior | Sequence diagrams for each mode; edge cases (retarget doesn't shrink `total_seconds`, finished calendar event dedup, SIGINT during stop modal, watch vs one-shot block-end skip lists) |
| **`config-reference.md`** | Every env var + CLI flag | Map each `AppConfig` field → env key → default → behavior impact; include `BLOCK_END_*` alias table (`chrome` → `Google Chrome`) |
| **`domain-model.md`** | Entities and invariants | `SessionKind` (manual \| calendar \| hard_stop), `CalendarEvent`, `AppConfig`, `BlockAction` enum; invariants: stroke fraction 0–1, shake uses `shake_intensity(remaining, total, cfg)`, calendar block_at = event_start − `CALENDAR_BLOCK_BEFORE_MINS` |
| **`interfaces.md`** | Target protocols (for rebuild) | Define abstract boundaries an agent should implement: `TimerInputParser`, `CalendarSource`, `WindowShaker`, `BlockEndExecutor`, `OverlayRenderer`, `SessionClock`, `ConfigProvider` — with method signatures and which macOS API sits behind each |
| **`module-map.md`** | Target package layout | Proposed tree (see below); maps **current symbol → target module** for every public function/class |
| **`macos-permissions.md`** | Platform prerequisites | Calendar Full Access, Accessibility for terminal, optional EventKit/ApplicationServices install; doctor-style checklist |
| **`testing-strategy.md`** | How to verify without manual Mac every time | Pure-Python unit tests: `input_parse`, `shake_intensity`, `calendar_block_target`, block-end name resolution; fakes for protocols; manual Mac checklist for PyObjC UI; keep `shake_test.py` as integration harness |
| **`migration-checklist.md`** | Ordered refactor steps | Extract shared math → extract mac/applescript → extract UI → introduce protocols → split CountdownApp orchestration from views → Watcher as thin coordinator; **no behavior change** gates between steps |

### Proposed target package layout (document only — do not implement)

```
tools/countdown/
  pyproject.toml              # package metadata, entry point countdown = countdown.main:main
  countdown/
    main.py                   # argparse only; dispatches watch | countdown
    config/
      env.py                  # load_dotenv, parsers
      settings.py             # AppConfig, merge_cli
    domain/
      session.py              # SessionKind, session metadata dataclass
      timer_math.py           # calendar_block_target, format_duration, stroke color helpers
      shake_curve.py          # shake_intensity + single _smoothstep
      lerp.py                 # shared _lerp
    input/
      parse.py                # parse_target_time, parse_quick_input
    calendar/
      models.py               # CalendarEvent
      monitor.py              # CalendarMonitor (implements CalendarSource)
    mac/
      run_loop.py             # pump, timer bridge
      accessibility.py        # FocusShaker backend
      applescript.py          # hide/minimize/foreground list
      workspace.py            # quit app, open URL (future)
      wifi.py                 # future: SSID detection
    block_end/
      resolver.py             # action_for_process, expand aliases
      executor.py             # apply_block_end_actions
    ui/
      stroke.py               # CountdownWindow/View
      hud.py                  # HUD + FinishControl
      stop_modal.py           # StopBlock*, dynamic lines factory (future)
      colors.py               # STROKE_BLUE, red-zone lerp
    session/
      controller.py           # CountdownApp — orchestrates, no drawRect_
    watcher/
      watcher.py              # Watcher + stdin poll
  docs/                       # all markdown above
  architecture.md             # or symlink → docs/architecture.md
  shake_test.py               # stays as dev harness; imports from countdown.mac.accessibility
  run                         # unchanged UX
```

### Symbol migration table (excerpt for `module-map.md`)

| Current location | Symbol | Target module |
|------------------|--------|---------------|
| `countdown.py` | `CountdownApp` | `session/controller.py` |
| `countdown.py` | `Watcher` | `watcher/watcher.py` |
| `countdown.py` | `FocusShaker` | `mac/accessibility.py` |
| `countdown.py` | `apply_block_end_actions` | `block_end/executor.py` |
| `countdown.py` | `StopBlockView/Window` | `ui/stop_modal.py` |
| `countdown.py` | `CountdownView/Window` | `ui/stroke.py` |
| `config.py` | `shake_intensity` | `domain/shake_curve.py` |
| `config.py` | `_smoothstep` | `domain/shake_curve.py` (delete duplicate) |
| `input_parse.py` | all | `input/parse.py` |
| `calendar_monitor.py` | all | `calendar/*` |

### Behavior tables agents must not get wrong

Document explicitly in `workflows.md` / `domain-model.md`:

1. **Shake window**: starts at `SHAKE_BEFORE_MINS` before end (or `SHAKE_START_FRACTION` of total if shorter); nudge ramp in first `SHAKE_NUDGE_SECONDS`; stops at `SHAKE_STOP_BEFORE_MINS` before zero.
2. **Calendar block target**: `event_start - CALENDAR_BLOCK_BEFORE_MINS`; skip if block_at ≤ now.
3. **Retarget**: only extends `total_seconds`, never shrinks — affects shake curve baseline.
4. **Block-on-end**: stop modal **above** screen saver level; 0.6s dismiss delay; stroke/HUD hidden during modal; actions run **after** dismiss on next pump tick.
5. **Watch block-end**: extra skip = terminal host apps; reactivate terminal after tidy.
6. **Calendar dedup**: `_finished_calendar_events` prevents re-trigger until event start passes.
7. **Skip shake apps**: terminal, Cursor, Python, system UI — never shaken.

### SOLID mapping (for `interfaces.md` intro)

| Principle | Current pain | Target fix |
|-----------|--------------|------------|
| **S** | `countdown.py` does CLI + UI + AX + AppleScript | One module per concern in package tree |
| **O** | New session kind requires editing CountdownApp stroke logic | `SessionKind` + stroke strategy registry |
| **L** | N/A (no inheritance) | Fakes implement same protocols as mac adapters |
| **I** | CountdownApp touches everything | Narrow protocols: shaker, block executor, overlay factory |
| **D** | Direct PyObjC/AppKit imports in session loop | Controller depends on protocols; mac/ holds implementations |

---

## What we are NOT doing in this task

- No code split, no new packages, no refactors
- No implementing calendar-calls / hard-stop features (only document as future session kinds)
- No commit unless you ask

---

## Suggested file creation order

1. `tools/countdown/architecture.md` — C4 + sequences + state (this plan's diagrams, polished)
2. `tools/countdown/docs/features.md` — feature list with acceptance criteria
3. `tools/countdown/docs/domain-model.md` + `config-reference.md`
4. `tools/countdown/docs/workflows.md` — edge cases from code review of [`CountdownApp`](tools/countdown/countdown.py) and [`Watcher`](tools/countdown/countdown.py)
5. `tools/countdown/docs/interfaces.md` + `module-map.md`
6. `tools/countdown/docs/macos-permissions.md` + `testing-strategy.md` + `migration-checklist.md`

After docs land, a separate task can execute `migration-checklist.md` step-by-step with tests after each extraction.
