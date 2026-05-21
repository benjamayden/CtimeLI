# CLAUDE.md — handoff notes

You are picking up this repo cold. Read this before doing anything.

## First action

```sh
git log --oneline -10
ls tools/countdown
cat tools/countdown/docs/README.md
```

That is the live state. This file is the durable context.

> **History note.** Earlier commits on this repo contain an abandoned Rust
> experiment (`crates/nebulaos-*`, an on-device LLM "thinking partner"). It is
> **not** in the working tree and is not this project. Ignore it. If you find a
> doc or comment referring to Whisper, Ollama, or `nebulaos-core`, it is stale.

## What this project is

A **macOS screen-edge countdown timer** for time-blind / ADHD work. It draws a
shrinking stroke around every display, glows the edges as zero nears, wiggles
the frontmost window in the final seconds, and can hard-block the screen at zero
and tidy your windows away. It also has a watch mode that auto-starts timers
from your calendar.

It lives entirely in `tools/countdown/`.

## The documentation IS the spec

`tools/countdown/docs/` is a complete, framework-agnostic blueprint. **Trust it
over the code** — if they disagree, the code is wrong (or the docs need a PR).
Read [`tools/countdown/docs/README.md`](tools/countdown/docs/README.md) first.

| Doc | For |
|-----|-----|
| `docs/architecture.md` | Layers, C4 diagrams, the dependency rule, invariants. |
| `docs/features.md` | What the app does, with acceptance criteria. |
| `docs/domain.md` | Every pure formula, the parser, the state machine. |
| `docs/ports.md` | Interface contracts for every adapter. |
| `docs/configuration.md` | Config fields, env vars, CLI flags. |
| `docs/edge-cases.md` | Bugs found, fixes, guards — **read before "simplifying".** |
| `docs/development.md` | Testing, review checklist, smell catalogue. |
| `docs/porting.md` | Rebuilding in Rust + Tauri or elsewhere. |

## Shape (memorize)

A **Ports & Adapters** package. Dependencies point inward; the domain is pure.

```
tools/countdown/countdown/
  domain/       PURE logic — math, curves, colours, timespec, session, calendar, blockend.
                No I/O, no platform calls. 100% unit-tested. Port verbatim.
  ports.py      Interfaces — one per external concern (Clock, Overlay, Shaker, …).
  app/          Orchestration — SessionRunner, WatchRunner. Depends on domain + ports only.
  adapters/     Concrete ports. macos/ (PyObjC/EventKit/AX/AppleScript), system/ (stdlib).
  composition.py + cli.py   Wiring + argparse. The only place adapters are constructed.
tools/countdown/tests/      pytest — domain exhaustive, app via fakes.
tools/countdown/docs/       the blueprint above.
```

**Invariant**: `domain/` and `app/` must never import `AppKit`, `objc`,
`EventKit`, `ApplicationServices`, or anything from `adapters/`. A grep gate
enforces it (`docs/development.md` §"Guard scripts"). This is what keeps the app
testable on Linux and portable to Rust.

## Branch

- Repo: `Lenniott/nebulaos`
- Working branch: `claude/python-refactor-architecture-docs-tXqtr` — develop and
  push here. Do not open a PR unless asked.

## Commands

```sh
cd tools/countdown
.venv/bin/pytest                       # must pass before commit (domain + app)
./run 15                               # macOS — 15-minute timer
./run watch                            # macOS — watch mode
./shake --seconds 20                   # macOS — wiggle tuning harness

# Guard gate — must print nothing:
grep -REn '^[[:space:]]*(import|from)[[:space:]].*(AppKit|objc|EventKit|ApplicationServices|adapters)' \
     countdown/domain countdown/app
```

## Status

- **Docs**: complete and authoritative.
- **Domain + app**: pure logic refactored out of the old 1864-line monolith,
  unit-tested, verified on Linux.
- **macOS adapters**: ported but **not machine-verified** (no Mac on CI). See
  `docs/edge-cases.md` §"Unverified surface" and `docs/development.md`
  §"Manual macOS checklist" before trusting them.

## What to do if the user asks…

- "What does it do?" → `docs/features.md`.
- "How is it built / why this shape?" → `docs/architecture.md`.
- "Re-implement / port it" → `docs/porting.md` + `docs/domain.md`.
- "Why is this weird line here?" → check `docs/edge-cases.md` first; it is
  probably a documented guard.
- "Add a feature" → `docs/development.md` §"How to add things". Ship it; do not
  refactor for elegance, do not add error handling for impossible cases.

## What NOT to do

- Don't let `domain/` or `app/` touch a platform SDK or an adapter.
- Don't re-introduce the monolith — new concerns get a module / a port.
- Don't revive the Rust `nebulaos` experiment; it is not this project.
- Don't `git reset --hard`, force-push, or skip hooks without explicit permission.
- Don't open a PR unless the user asks.
