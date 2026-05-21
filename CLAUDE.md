# CLAUDE.md — handoff notes

You are picking up nebulaos cold. Read this before doing anything.

## First action

```sh
git log --oneline -10
cat architecture.md | tail -40
```

That's the live state. This file is the durable context the user expects you to know.

## What this project is

Rust workspace for a macOS-only thinking-partner CLI for ADHD creative work.
Listens (mic), watches (frontmost-app focus), talks back (TTS + on-device LLM).
**Read-only over the user's work — never edits, opens, or acts.**

The vision doc is `./PRD`. **PRD is the spec, not data the app consumes.** Past
me made that mistake — the user corrected hard. Don't repeat it.

PRD success criterion (§7 v0.1 MVP test): a 1hr website-copy session with vs
without Nebulaos. The question: "did the task get done?"

## Branch

- Repo: `Lenniott/nebulaos`
- Working branch: `claude/mvp-read-prd-PHi2j` — develop and push here.
- `main` is untouched. No PR exists. Don't open one unless the user asks.

## Shape (memorize)

```
crates/
  nebulaos-core/   library  — ALL logic. Frontend-agnostic. INVARIANT: no
                              println!/print!/eprint!/indicatif/clap here.
                              Grep verifies this on every commit.
  nebulaos-cli/    binary   — terminal frontend (clap + indicatif). A future
                              nebulaos-tauri sits next to it, depends on core.
PRD                vision doc (do not modify)
architecture.md    C4 diagrams + slice status (update when shape changes)
README.md          user-facing build + Mac setup recipe
CLAUDE.md          this file
```

The session-machine contract:
```rust
// nebulaos-core/src/session/mod.rs
pub fn run(commands: mpsc::Receiver<Command>, total: Duration,
           partner: Option<Arc<dyn Partner>>) -> impl Stream<Item = SessionEvent>
```
Every frontend (CLI today, Tauri later) sends `Command`, renders `SessionEvent`.
That's the whole API surface a UI needs.

## Where things live

| Concern | File |
|---|---|
| session state machine | `crates/nebulaos-core/src/session/mod.rs` |
| partner system prompt (PRD §8 voice) | `crates/nebulaos-core/src/partner/prompt.rs` |
| Ollama client | `crates/nebulaos-core/src/partner/ollama.rs` |
| Claude fallback | `crates/nebulaos-core/src/fallback/claude.rs` |
| file-backed RAG | `crates/nebulaos-core/src/rag/jsonl.rs` |
| session log + export | `crates/nebulaos-core/src/log/jsonl.rs` |
| data-dir resolution | `crates/nebulaos-core/src/paths.rs` |
| workspace classifier (name → Attention) | `crates/nebulaos-core/src/vision/mod.rs` |
| macOS mic (cpal) | `crates/nebulaos-core/src/audio/mac_mic.rs` |
| macOS TTS (say) | `crates/nebulaos-core/src/audio/mac_say.rs` |
| Whisper transcriber | `crates/nebulaos-core/src/stt/mac_whisper.rs` |
| NSWorkspace focus poller | `crates/nebulaos-core/src/focus/mac_nsworkspace.rs` |
| CLI mac glue (doctor, focus relay, voice prompt) | `crates/nebulaos-cli/src/mac.rs` |
| CLI entry + flag wiring | `crates/nebulaos-cli/src/main.rs` |
| TTY rendering | `crates/nebulaos-cli/src/ui.rs` |

## Status (as of last commit on this branch)

What's verified on Linux:
- 18 tests green, clippy `-D warnings` clean.
- Core stays frontend-agnostic (grep verified).
- End-to-end smoke: ingest → recall → start (with `--goal`) → export.

What's UNVERIFIED (written blind from Linux for macOS):
- `mac_mic.rs` — cpal 0.15 stream-config conversion via `.into()`. Likely fine but unverified.
- `mac_whisper.rs` — whisper-rs 0.13 API; the crate has churned: `WhisperContext::new_with_params`, `state.full_n_segments()`, `convert_integer_to_float_audio`. Check version compatibility first.
- `mac_nsworkspace.rs` — objc2-app-kit 0.2 method names (`sharedWorkspace`, `frontmostApplication`, `localizedName`). Features in Cargo.toml: `NSWorkspace`, `NSRunningApplication`.
- `mac.rs` — glue, plus reads bytes from stdin for push-to-talk. Should work; FFI risk is in the three files above.

I could not cross-compile to verify (ring's C build wants osxcross, not worth it).

## Pick-up procedure on macOS

1. `cargo run -p nebulaos-cli -- doctor` — surfaces missing pieces fast.
2. If `cargo build` fails before doctor runs, fix the FFI in the four files above (in order of likelihood: whisper > nsworkspace > cpal > mac.rs).
3. Common fixes:
   - whisper-rs API drift → check current crate docs, adjust `new_with_params`/`full_n_segments`/`convert_integer_to_float_audio` signatures.
   - objc2-app-kit feature flags → if a method's missing, add the right feature.
   - cpal `SupportedStreamConfig` → `StreamConfig` via `.config()` if `.into()` doesn't resolve.
4. Once it builds: run `doctor`, address its ✗ marks (model file, Ollama, mic permission).
5. Then the concept-test command from `README.md`:
   ```sh
   cargo run -p nebulaos-cli -- start --mic --voice --ollama \
     --workspaces "Figma,Notion,Code,Pages,TextEdit" --minutes 25
   ```

## Commands

```sh
cargo build --workspace
cargo test --workspace                          # must pass before commit
cargo clippy --workspace -- -D warnings         # must pass before commit
grep -RE 'println!|print!|eprint!|indicatif|clap' crates/nebulaos-core/src
                                                 # must return nothing
cargo run -p nebulaos-cli -- doctor             # macOS only, fast wiring check
cargo run -p nebulaos-cli -- start --goal "..." --minutes 1   # quick smoke
NEBULAOS_DATA_DIR=/tmp/x cargo run -p nebulaos-cli -- export  # isolated test
```

## Invariants (don't break)

1. `nebulaos-core` has no terminal-specific code. Grep is the gate.
2. `Partner` is `async_trait`. New impls drop in via `Arc<dyn Partner>`.
3. `AudioOutput`, `SpeechToText`, `Rag`, `Fallback`, `FocusSource` traits are the swap points. Honor them.
4. The session machine doesn't know what frontend is rendering — keep it that way.
5. Whisper expects 16 kHz mono i16. The mic capture resamples to that before calling `transcribe`. If you change one, change the other.

## Decisions already made (don't relitigate)

- TTS via `say` for MVP. Kokoro is a later swap behind `AudioOutput`. Reason: Kokoro ONNX is heavy, `say` ships with every Mac.
- Drift via name-based `WorkspaceClassifier`. Candle vision is a later swap behind the same call site. Reason: ML model adds days; declared workspaces work today.
- RAG file-backed (`JsonlRag`). LanceDB is a later swap behind the `Rag` trait. Reason: LanceDB needs an embedding model; substring is enough for concept validation.
- Whisper model NOT bundled in repo. User downloads via the curl in README. Reason: ~75MB, no good way to vendor.
- Cross-compile from Linux NOT attempted. Reason: ring's C build needs osxcross.

## What to do if the user asks…

- "What does this do?" → cite `PRD` §1-3, point at `architecture.md`, list current slice status.
- "What's working?" → the table in "Status" above. Be honest about unverified macOS code.
- "Why did you …?" → check "Decisions already made" first.
- "Ship X" → ship X. Don't refactor for elegance. Don't add error handling for impossible cases. Don't add backwards-compat shims (this codebase has no users yet).

## What NOT to do

- Don't refactor when the request is a feature.
- Don't add Kokoro / Candle / LanceDB unless explicitly asked.
- Don't `git reset --hard`, force-push, or skip hooks without explicit permission.
- Don't put `claude-opus-*` model identifiers in commits, PR bodies, or code comments.
- Don't open a PR unless the user asks.
- Don't make the user re-type build commands they already know — point them at `README.md`.

## Common pitfalls I've already hit on this project

- Misread "make the MVP read the PRD" as "load PRD as input". Wrong. The PRD is the SPEC for the app. The MVP IS the app described in the PRD. (User's correction was sharp: "Your supposed to read this and make the app dumb ass". Read it as a useful signal.)
- Asked too many clarifying questions before reading the room. The user wants momentum. Ask only when an answer materially changes the design.
- Wasted time trying to cross-compile to macOS from Linux. ring won't build without osxcross. Don't try again.

## Slice list (history)

1. Workspace + skeleton + C4
2. Goal declaration plumbing (stdin)
3. Ollama partner + voice-spec prompt + chat subcommand
3b. Partner wired into session loop
4. Drift state machine + `Command::Focus`
5. File-backed RAG + ingest/recall CLI
6. JsonlSessionLog + export + ClaudeFallback
7. macOS IO — mic+Whisper, say TTS, NSWorkspace, doctor (unverified)

Next likely slice: concept-test feedback → fix macOS FFI → first real session.
