//! Speech-to-text. PRD §6: Whisper Tiny on-device.
//!
//! ## Status
//!
//! Slice 2b (TODO, macOS): add `whisper-rs` as a macOS-gated dep, load the
//! `ggml-tiny.bin` model from `~/.nebulaos/models/`, expose a
//! `WhisperTranscriber` impl of `SpeechToText`. The trait below already
//! matches the i16 PCM contract `cpal` will produce.

use anyhow::Result;

pub trait SpeechToText: Send + Sync {
    fn transcribe(&self, pcm: &[i16]) -> Result<String>;
}
