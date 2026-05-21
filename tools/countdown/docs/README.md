# Countdown — documentation set

A macOS screen-edge countdown timer for time-blind / ADHD work. It draws a
shrinking stroke around every display, glows the screen edges as zero
approaches, physically wiggles the frontmost window in the final seconds, and
can hard-block the screen at zero and tidy your windows away.

This folder is the **blueprint**. It is written to be *framework-agnostic*: it
describes *what the system does* and *why it is shaped the way it is*, not the
Python syntax. You should be able to hand this folder to an agent (or a human)
and have them rebuild the app in Rust + Tauri, Swift, or anything else, without
reading the original source.

## How the app is layered

The codebase is a **Ports & Adapters** (hexagonal) design. Read
[`architecture.md`](architecture.md) first — every other doc assumes it.

```
Domain  ──>  pure logic, no I/O, no platform calls. Deterministic. 100% testable.
Ports   ──>  interfaces. The contract between the app and the outside world.
App     ──>  orchestration. Depends only on Domain + Ports.
Adapters──>  concrete Port implementations (macOS, system). Swappable.
Compose ──>  builds adapters, injects them, parses CLI. The only "wiring".
```

The **dependency rule**: arrows point inward. Domain knows nothing. Adapters
know Ports. Nothing imports an Adapter except the composition root. Honor this
and the app stays testable and portable; break it and you get the 1864-line
monolith this refactor replaced.

## Reading order

| # | Doc | Read it when you want to… |
|---|-----|---------------------------|
| 1 | [`architecture.md`](architecture.md) | Understand the layers, C4 diagrams, the dependency rule, and the invariants every change must keep. |
| 2 | [`features.md`](features.md) | Know what the product does — feature inventory with acceptance criteria and behaviour tables. |
| 3 | [`domain.md`](domain.md) | Re-implement the pure logic exactly — every formula, the time parser, the session state machine. |
| 4 | [`ports.md`](ports.md) | Implement an adapter — every interface contract with pre/post-conditions and failure modes. |
| 5 | [`configuration.md`](configuration.md) | Look up a config field, env var, CLI flag, or precedence rule. |
| 6 | [`edge-cases.md`](edge-cases.md) | See the bugs we found, how they were fixed, and the traps still lurking. |
| 7 | [`development.md`](development.md) | Test, review, or extend the code — testing strategy, review checklist, smell catalogue. |
| 8 | [`porting.md`](porting.md) | Rebuild this in another framework — Rust + Tauri port map and what is / isn't portable. |

## Status

- **Documentation**: complete and authoritative. If code disagrees with these
  docs, the code is wrong (or the docs need a PR — keep them in lockstep).
- **Python implementation**: refactored from a single 1864-line file into the
  layered package described here. Pure domain logic is unit-tested and verified
  on Linux. macOS adapters (PyObjC / EventKit / Accessibility / AppleScript)
  are **written but not machine-verified** — see
  [`edge-cases.md`](edge-cases.md) §"Unverified surface".

## One-paragraph summary for an agent in a hurry

Build five layers. `domain/` is pure functions and a state machine — port it
verbatim, it has no platform calls. `ports.py` is interfaces — one per external
concern (clock, logger, overlay, shaker, calendar, …). `app/` orchestrates
domain + ports and is the heart of the program. `adapters/` implements ports
against the host OS. `composition.py` + `cli.py` wire it together. Test the
domain exhaustively and the app with fake adapters; the platform adapters are
verified by hand. Never let `app/` or `domain/` import an adapter.
