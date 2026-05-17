# nebulaos

Calm the nebulous chaos. A read-only thinking partner for ADHD creative work — listens, watches the screen, talks back via an on-device LLM, never touches your work.

**Status:** slice 1 — skeleton. Workspace, session loop, terminal progress bar. No audio, vision, or model integration yet.

## Build & run

```sh
cargo run -p nebulaos-cli -- start
cargo run -p nebulaos-cli -- start --minutes 25
cargo run -p nebulaos-cli -- export
```

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
