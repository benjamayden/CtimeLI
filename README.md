# nebulaos

Calm the nebulous chaos. A read-only thinking partner for ADHD creative work — listens, watches the screen, talks back via an on-device LLM, never touches your work.

**Status:** slice 6 — log, export, fallback all online. Sessions write JSONL to `~/.nebulaos/sessions/`, `nebulaos export` rolls up the latest, `nebulaos fallback` calls Claude when Hermes isn't sharp enough. RAG is file-backed (LanceDB swap is 5b). Voice in (mic+Whisper) and voice out (Kokoro TTS) are macOS-gated stubs — trait contracts in place; impls land when you switch to the Mac.

## Build & run

```sh
cargo run -p nebulaos-cli -- start --goal "draft the hero" --minutes 25
cargo run -p nebulaos-cli -- start --goal "..." --ollama         # live partner

cargo run -p nebulaos-cli -- ingest path/to/brief.md
cargo run -p nebulaos-cli -- recall "homepage hero" --k 5

cargo run -p nebulaos-cli -- chat "I'm stuck on the hero"        # one-shot Hermes
cargo run -p nebulaos-cli -- fallback "session went off-task at 23 min"  # one-shot Claude

cargo run -p nebulaos-cli -- export
```

Local `Ollama` daemon required for `chat` and `--ollama`: `ollama pull hermes3:8b`. `fallback` reads `ANTHROPIC_API_KEY` from env.

Data lives in the OS data dir (macOS: `~/Library/Application Support/io.lenniott.nebulaos`). Override via `NEBULAOS_DATA_DIR`.

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
