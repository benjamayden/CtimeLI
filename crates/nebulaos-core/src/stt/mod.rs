//! Speech-to-text. PRD §6: Whisper Tiny on-device.

use anyhow::Result;

#[cfg(target_os = "macos")]
mod mac_whisper;

#[cfg(target_os = "macos")]
pub use mac_whisper::WhisperTranscriber;

pub trait SpeechToText: Send + Sync {
    fn transcribe(&self, pcm: &[i16]) -> Result<String>;
}

