# Branch Changes — fixes

This document summarizes the changes currently staged in branch `fixes`, why
they were made, and what test coverage was added.

## Scope

- Installer and runner bootstrap hardening for Python version compatibility.
- Watch-mode calendar dedupe bug fix (prevent same event from re-triggering
  after completion).
- Composition import fix for terminal UI helpers used by permission setup.
- Regression tests for watch-mode completion behavior.

## Change Summary

### 1) Python bootstrap hardening

Files:
- `install.sh`
- `run`

What changed:
- Added Python interpreter selection with minimum version gate (>= 3.11).
- Added explicit compatibility check for existing `.venv` Python.
- Switched package install invocations to `python -m pip`.
- Added a quiet bootstrap step to upgrade `pip`, `setuptools`, and `wheel`.
- Extended Calendar usage-description patch path with a macOS admin-dialog
  fallback when direct sudo path fails.

Why:
- Prevents creating or reusing an incompatible virtual environment that later
  fails on PyObjC dependency resolution or runtime behavior.
- Improves deterministic bootstrap behavior across common macOS Python layouts.
- Increases likelihood that calendar permission dialogs can be enabled without
  manual plist surgery.

### 2) Watch-mode calendar completion dedupe fix

File:
- `src/ctimeli/app/watch_runner.py`

What changed:
- In `WatchRunner._pump_current`, finished calendar sessions are now recorded
  to `_finished_events` whenever they complete cleanly (calendar + event id +
  not interrupted), instead of only when completion went through the
  block-on-end path.

Why:
- Previous behavior only deduped when `session.blocked` was true.
- If block-on-end was disabled, a completed calendar session could immediately
  be considered eligible again and auto-start once more for the same event.
- New behavior matches watch-mode intent: one event should not auto-fire again
  after completion.

### 3) Composition terminal-ui import fix

File:
- `src/ctimeli/composition.py`

What changed:
- Added import of `indent` and `tagged` from `ctimeli.terminal_ui`.

Why:
- `run_permissions_setup` prints guidance using these helpers; without import,
  that flow can raise `NameError`.

### 4) Watch-runner regression tests

File:
- `tests/test_watch_runner.py`

What changed:
- Added `test_completed_calendar_session_without_block_does_not_restart`.

Why:
- Locks in the non-blocking completion behavior so the dedupe regression does
  not return.

## Behavior Diagrams

### A) Calendar completion dedupe in watch mode

Mermaid source: [docs/diagrams/branch-changes-calendar-dedupe.mmd](docs/diagrams/branch-changes-calendar-dedupe.mmd)

```text
Calendar session running
  -> session ended?
     no  -> keep session active
     yes -> completed calendar event?
            yes -> record finished event id -> clear current session -> idle
            no  -> skip dedupe             -> clear current session -> idle
```

### B) Bootstrap interpreter selection

Mermaid source: [docs/diagrams/branch-changes-bootstrap.mmd](docs/diagrams/branch-changes-bootstrap.mmd)

```text
Start install or run bootstrap
  -> existing venv present?
     no  -> pick Python 3.11 or newer
         -> create .venv
         -> upgrade pip setuptools wheel
         -> install requirements
     yes -> venv Python compatible?
            no  -> stop and ask to recreate venv
            yes -> install requirements
```

## Tests Added / Updated

New or relevant coverage:
- `tests/test_watch_runner.py::test_completed_calendar_session_without_block_does_not_restart`
- Existing guard retained:
  `tests/test_watch_runner.py::test_completed_calendar_session_adds_to_finished_events`

Recommended validation commands:

```bash
.venv/bin/python -m pytest tests/test_watch_runner.py -q
.venv/bin/python -m pytest -q
```

Verification run on this branch:
- Focused watch tests: `28 passed`.
- Full suite: `213 passed, 2 skipped`.

## Risk Notes

- The watch-mode dedupe change intentionally keeps interrupted sessions out of
  `_finished_events` so user-aborted replacements do not suppress legitimate
  future starts.
- Python bootstrap gating may stop previously permissive paths that used older
  Python binaries; this is expected and intentional.
