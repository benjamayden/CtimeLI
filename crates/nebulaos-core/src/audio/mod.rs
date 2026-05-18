//! Audio IO. PRD §6: Whisper Tiny in, Kokoro out.
//!
//! ## Status
//!
//! - Slice 3c (macOS): `SaySpeech` shells out to `/usr/bin/say` for TTS.
//!   Works on every Mac without any model file or extra deps; swap to a
//!   Kokoro ONNX `AudioOutput` impl later.
//! - Slice 2b (macOS, in progress): `MacMicCapture` via `cpal`, paired with
//!   `stt::WhisperTranscriber` for speech-to-text on goal declaration.

use anyhow::Result;

#[cfg(target_os = "macos")]
mod mac_mic;
#[cfg(target_os = "macos")]
mod mac_say;

#[cfg(target_os = "macos")]
pub use mac_mic::{MacMicCapture, CaptureHandle};
#[cfg(target_os = "macos")]
pub use mac_say::SaySpeech;

pub trait AudioInput: Send + Sync {
    fn start(&mut self) -> Result<()>;
    fn stop(&mut self) -> Result<()>;
}

pub trait AudioOutput: Send + Sync {
    fn speak(&self, text: &str) -> Result<()>;
}

