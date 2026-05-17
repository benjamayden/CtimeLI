//! Speech-to-text. PRD §6: Whisper Tiny on-device. Slice 2.

use anyhow::Result;

pub trait SpeechToText: Send + Sync {
    fn transcribe(&self, pcm: &[i16]) -> Result<String>;
}
