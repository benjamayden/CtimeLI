# nebulaos

Calm the nebulous chaos. A read-only thinking partner for ADHD creative work — listens, watches the screen, talks back via an on-device LLM, never touches your work.

**Status:** concept-test ready on macOS. Voice in (mic + Whisper), voice out (`say`), focus-based drift detection, partner via local Ollama, RAG, session log, Claude fallback. macOS-only paths haven't been compile-tested from the dev container — first build on the Mac will surface any glue issues. See `architecture.md` for the C4 view.

## Build & run

```sh
cargo run -p nebulaos-cli -- start --goal "draft the hero" --minutes 25
cargo run -p nebulaos-cli -- export
cargo run -p nebulaos-cli -- chat "I'm stuck on the hero"
cargo run -p nebulaos-cli -- fallback "session went off-task at 23 min"
cargo run -p nebulaos-cli -- ingest path/to/brief.md
cargo run -p nebulaos-cli -- recall "homepage hero" --k 5
```

Local Ollama required for `chat` and `--ollama`: `ollama pull hermes3:8b`. Claude fallback reads `ANTHROPIC_API_KEY` from env.

## Mac setup (concept-test recipe)

```sh
# 1. Toolchain
xcode-select --install
brew install cmake ollama

# 2. Models
ollama serve &
ollama pull hermes3:8b
mkdir -p "$HOME/Library/Application Support/io.lenniott.nebulaos/models"
curl -L -o "$HOME/Library/Application Support/io.lenniott.nebulaos/models/ggml-tiny.bin" \
  https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-tiny.bin

# 3. Build (first cargo build downloads cpal, whisper-rs, objc2)
cargo build -p nebulaos-cli

# 4. Verify the wiring
cargo run -p nebulaos-cli -- doctor

# 5. Run a 25-min concept test
cargo run -p nebulaos-cli -- start \
  --mic \
  --voice \
  --ollama \
  --workspaces "Figma,Notion,Code,Pages,TextEdit" \
  --minutes 25
```

What that gives you:
- Push-to-talk goal declaration (press Enter to start, Enter to stop).
- Hermes via Ollama generates the welcome + every drift nudge.
- macOS `say` reads partner lines aloud while they print.
- NSWorkspace polls the frontmost app every 500ms; anything not in `--workspaces` counts as off-task; 60s of accumulated off-task fires a soft check-in (5-min cooldown).
- Everything writes to `~/Library/Application Support/io.lenniott.nebulaos/sessions/`.

First mic use prompts for microphone permission. If you skip it, capture returns silence and the goal falls back to a typed prompt.

Faster Whisper (Metal-accelerated): `cargo run --features mac-accel -p nebulaos-cli -- start ...`.

## Layout

```
crates/
  nebulaos-core/   library — session state, partner, audio, vision, stt, focus, rag, log, fallback, paths
  nebulaos-cli/    binary — terminal frontend (clap + indicatif + macOS glue)
PRD                vision doc
architecture.md    C4 diagrams (system context, containers, components)
```

The core never imports `indicatif`, `clap`, or `println!` — a future Tauri frontend drops in by depending on `nebulaos-core` and rendering the same `SessionEvent` stream.

## Data dir

macOS: `~/Library/Application Support/io.lenniott.nebulaos/`. Override with `NEBULAOS_DATA_DIR=/path`.

Contains `sessions/`, `rag/`, `models/`. Delete anything any time — it's all yours.
