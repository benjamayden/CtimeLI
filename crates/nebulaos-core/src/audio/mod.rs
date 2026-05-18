//! Audio IO. PRD §6: Whisper Tiny in, Kokoro out.
//!
//! ## Status
//!
//! - Slice 2b (TODO, macOS): real `cpal` mic capture for `AudioInput`. Pull
//!   the [`cpal`] crate behind `[target.'cfg(target_os = "macos")']`, build
//!   a stream that hands i16 PCM to the `stt::SpeechToText` impl.
//! - Slice 3c (TODO, macOS): real Kokoro TTS via `ort` for `AudioOutput`.
//!   Bundle the ONNX model in `assets/`, load it at session start.
//!
//! Today the traits are wired into nothing — `nebulaos start` skips mic/voice
//! entirely. The session machine drives off `Command::Focus` and stdin goal
//! declaration, so the rest of the pipeline is already exercised.

use anyhow::Result;

pub trait AudioInput: Send + Sync {
    fn start(&mut self) -> Result<()>;
    fn stop(&mut self) -> Result<()>;
}

pub trait AudioOutput: Send + Sync {
    fn speak(&self, text: &str) -> Result<()>;
}
