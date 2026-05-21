# Porting guide — rebuilding in another framework

The whole point of the layered design is that a rewrite is a **re-implementation
of adapters**, not a re-derivation of behaviour. This guide maps the blueprint
onto Rust + Tauri specifically, and states the general rule for any target.

If you read nothing else: **port the domain first, verbatim, with its tests.
Everything else hangs off a green domain.**

---

## 1. What is portable vs. platform-coupled

| Layer | Portable? | Effort in a rewrite |
|-------|-----------|---------------------|
| `domain/` | **100% portable** | Mechanical translation. Same formulas, same state table, same tests. This is ~40% of the real logic and the part that is *hard to get right* — and it is already specified exactly in [`domain.md`](domain.md). |
| `ports.py` | **100% portable** | Becomes traits / interfaces. Signatures use only domain types, so they translate directly. |
| `app/` | **~95% portable** | Orchestration logic is portable; only the *idiom* of "inject a dependency" changes. |
| `adapters/` | **0% portable** | Rewritten per platform/framework. This is the intended cost. |
| `cli.py` / `composition.py` | rewritten | Small; argument parsing + wiring. |

So a port is: translate domain + ports + app (the inner triangle, fully
specified by these docs), then write fresh adapters for the new stack.

## 2. The general porting procedure

1. **Domain.** Translate `domain/` and its tests
   ([`development.md`](development.md) §2 tier 1). Do not continue until the
   domain test suite is green in the new language. The [`domain.md`](domain.md)
   formulas and the parsing/transition tables are your spec — match every row.
2. **Ports.** Translate `ports.py` into the target's interface construct
   (Rust traits, Swift protocols, TS interfaces). Contracts in
   [`ports.md`](ports.md).
3. **App.** Translate `app/` against those interfaces. Test it with fakes —
   tier 2. Still no platform code.
4. **Adapters.** Implement each port for the new platform. Verify by hand
   ([`development.md`](development.md) §2 tier 3 / the manual checklist).
5. **Composition + entry.** Wire it up.

Keep the dependency rule ([`architecture.md`](architecture.md) §2) in the new
language — it is what made step 4 the *only* platform-specific step.

---

## 3. Rust + Tauri map

### Domain → a plain Rust crate (`countdown-core`)

Pure functions and an enum state machine. No `tokio`, no `tauri`, no `std::time`
calls inside it — `now` is a parameter, exactly as in Python.

- `f64` for the curve maths; the formulas in [`domain.md`](domain.md) are
  language-neutral.
- `SessionState` → a Rust `enum`; the transition table → a `match` in
  `Session::apply(event)`. Rust's exhaustive `match` makes the "illegal
  combination" class of bug (#15) *unrepresentable* — a genuine upgrade.
- `RenderFrame` → a `#[derive(Clone, Copy)] struct`.
- `CalendarEvent`, `AppConfig` → plain structs.
- `BlockAction` → an `enum`.
- Time: take `chrono::DateTime<Local>` (or `OffsetDateTime`) as a parameter.
- Tests: `#[cfg(test)]` modules, one per the tier-1 list. Port the tables 1:1.

### Ports → Rust traits

```rust
trait Clock           { fn now(&self) -> DateTime<Local>; fn monotonic(&self) -> f64; }
trait Logger          { fn info(&self, m: &str); fn warn(&self, m: &str); fn error(&self, m: &str); }
trait CountdownOverlay{ fn show(&mut self); fn render(&mut self, f: &RenderFrame); /* … */ }
trait WindowShaker    { fn apply(&mut self, dx: f64, dy: f64) -> bool; fn restore(&mut self); }
// … one trait per port in ports.md
```

Inject as `Box<dyn Trait>` or generics. The fakes become test structs
implementing the same traits — Liskov holds by construction.

### Adapters → Tauri + macOS crates

| Port | Python adapter (today) | Rust + Tauri replacement |
|------|------------------------|--------------------------|
| `Clock` | `datetime` / `time.monotonic` | `chrono::Local::now()` / `std::time::Instant`. **Portable enough to keep generic.** |
| `Logger` | stderr writer | `log` + `env_logger`, or Tauri's logging plugin. |
| `FrameScheduler` | `NSTimer` on the run loop | Tauri's event loop + a `~16 ms` timer, or `requestAnimationFrame` if the overlay is a webview. |
| `CountdownOverlay` | borderless click-through `NSWindow` | A Tauri window: `transparent: true`, `decorations: false`, `always_on_top: true`, `setIgnoreCursorEvents(true)` for click-through, `skipTaskbar`. Draw the stroke/glow on a `<canvas>` in the webview, **or** an `objc2` `NSWindow` for a non-webview overlay. |
| `StopOverlay` | full-screen modal `NSWindow` above screen-saver level | A fullscreen, focused Tauri window; set its level above the screen saver via `objc2` (`NSScreenSaverWindowLevel + 1`) since Tauri has no API for that. |
| `WindowShaker` | Accessibility AX API | The **same Accessibility C API** via the `accessibility` crate or raw `objc2` — `AXUIElementCreateApplication`, `kAXPositionAttribute`. The logic is identical; only the FFI binding changes. |
| `AppControl` | `NSWorkspace` / `NSApp` | `objc2-app-kit`: `NSWorkspace::sharedWorkspace`, `runningApplications`, activation policy. |
| `BlockEndExecutor` | `NSRunningApplication.terminate` + `osascript` | `NSRunningApplication` terminate via `objc2`; for hide/minimize either keep `osascript` (`std::process::Command`) or use Accessibility `AXMinimized`. |
| `CalendarSource` | EventKit via PyObjC | EventKit via `objc2-event-kit`. The async permission request maps to a channel the `ensure_access` call blocks on. |
| `InputSource` | non-blocking stdin (`fcntl`) | If watch mode keeps a terminal: a `std::thread` reading stdin into an `mpsc` channel (cleaner than `O_NONBLOCK` — and sidesteps bug #18 entirely). If watch mode becomes a GUI, this port disappears. |
| `SignalListener` | `signal.signal` | The `ctrlc` crate, or `tokio::signal`. |
| `EnvSource` | hand-rolled `.env` parser | The `dotenvy` crate — but read it into a map, **do not** use its `dotenv()` that mutates the process env (keep fix #5). |

### A note on the overlay decision

Tauri's natural overlay is a transparent webview window — draw the stroke and
glow on a `<canvas>`. That is the easiest path and the glow becomes a *real*
gradient again (bug #19 was a PyObjC/Python-3.14 quirk, not a macOS one — it
does not follow you to Rust). If you want a webview-free overlay, drop to
`objc2` `NSWindow` directly; the C4 shape is unchanged either way because the
overlay is hidden behind the `CountdownOverlay` port.

### Composition

A Rust composition root builds the concrete adapter structs and hands them
(boxed or generic) to `SessionRunner` / `WatchRunner`. `clap` replaces
`argparse` for `cli.rs`. Tauri's `Builder` setup hook is a fine place for the
wiring if the app is GUI-first.

---

## 4. Porting to other targets — the rule

For Swift, a TypeScript/Electron build, anything else: the procedure in §2 is
unchanged. Only the §3 table is rewritten. The constants that travel with the
domain regardless of language:

- `FRAME_INTERVAL = 1/60 s`, and `dt` floored at it (guard #12).
- `DISPLAY_SMOOTH_RATE = 9.0`, pulse phase advance `0.85`/s.
- `_STOP_DISMISS_DELAY = 0.6 s` (guard #7).
- `STROKE_BLUE`, `STROKE_RED` ([`domain.md`](domain.md) §3).
- All default config values ([`configuration.md`](configuration.md)).
- The full parsing table and the session transition table ([`domain.md`](domain.md)).

## 5. Pitfalls that survive a port

These are *behaviours*, not Python bugs — re-create the guards in any language:

- **#12 zero-`dt` freeze** — any frame loop can coalesce two ticks. Floor `dt`.
- **#7 dismiss lockout** — any block overlay that steals focus needs the 0.6 s
  input lockout, or an in-flight keystroke dismisses it instantly.
- **#8 retarget never shrinks `total_seconds`** — the stroke jumps backwards
  otherwise. This is in [`domain.md`](domain.md) §7 "Retarget".
- **Window-shaker restore** — always capture the original position and restore
  it; a crash mid-wiggle must not leave the user's window displaced. Consider a
  panic hook / `Drop` impl that calls `restore()`.
- **#28 ambiguous hours** — keep "nearest occurrence" parsing; it is by design.

Pitfalls that **do not** travel (Python/PyObjC-specific — feel free to drop the
workaround): **#19** (`NSGradient` crash) and **#18** (`O_NONBLOCK` on shared
stdin — gone if you use a reader thread).
