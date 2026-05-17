//! Audio IO. PRD §6: Whisper Tiny in, Kokoro out. Slice 2/3.

use anyhow::Result;

pub trait AudioInput: Send + Sync {
    fn start(&mut self) -> Result<()>;
    fn stop(&mut self) -> Result<()>;
}

pub trait AudioOutput: Send + Sync {
    fn speak(&self, text: &str) -> Result<()>;
}
