# nebulaos

Calm the nebulous chaos. A read-only thinking partner for ADHD creative work — listens, watches the screen, talks back via an on-device LLM, never touches your work.

**Status:** slice 3 — partner online. Ollama HTTP client wired with the PRD §8 voice spec as the system prompt. `nebulaos chat` round-trips against a local Hermes. Session loop still uses the stub welcome; slice 3b wires the live partner into the tick loop.

## Build & run

```sh
cargo run -p nebulaos-cli -- start
cargo run -p nebulaos-cli -- start --minutes 25
cargo run -p nebulaos-cli -- start --goal "draft the homepage hero"
cargo run -p nebulaos-cli -- chat "I'm stuck on the hero" --context "goal: homepage copy"
cargo run -p nebulaos-cli -- export
```

`chat` requires a local Ollama daemon. Pull a Hermes model first: `ollama pull hermes3:8b`.

`Ctrl-C` ends the session cleanly.

## Layout

```
crates/
  nebulaos-core/   library — session state, all component traits. Frontend-agnostic.
  nebulaos-cli/    binary — terminal frontend (clap + indicatif). Swappable with a Tauri app later.
PRD                vision doc
architecture.md    C4 diagrams (system context, containers, components)
```

The core never imports `indicatif`, `clap`, or `println!` — a future Tauri frontend drops in by depending on `nebulaos-core` and rendering the same `SessionEvent` stream.

## Roadmap

See `PRD` §7 (MVP / v1.1 / v2.0) and the slice list in `architecture.md`.
