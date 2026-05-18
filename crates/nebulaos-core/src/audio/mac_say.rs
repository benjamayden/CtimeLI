//! macOS TTS via the built-in `say` binary. Zero deps, works on every Mac
//! since forever, runs offline. PRD §6 calls for Kokoro ONNX eventually —
//! `say` gets us to a testable presence today; swapping to Kokoro is a
//! local change inside `speak()`.

use std::process::{Command, Stdio};

use anyhow::{Context, Result};

use crate::audio::AudioOutput;

pub struct SaySpeech {
    voice: Option<String>,
    rate: Option<u32>,
}

impl SaySpeech {
    pub fn new() -> Self {
        Self { voice: None, rate: None }
    }

    pub fn with_voice(mut self, voice: impl Into<String>) -> Self {
        self.voice = Some(voice.into());
        self
    }

    pub fn with_rate(mut self, words_per_minute: u32) -> Self {
        self.rate = Some(words_per_minute);
        self
    }
}

impl Default for SaySpeech {
    fn default() -> Self {
        Self::new()
    }
}

impl AudioOutput for SaySpeech {
    fn speak(&self, text: &str) -> Result<()> {
        let mut cmd = Command::new("say");
        if let Some(v) = &self.voice {
            cmd.arg("-v").arg(v);
        }
        if let Some(r) = self.rate {
            cmd.arg("-r").arg(r.to_string());
        }
        cmd.arg(text);
        cmd.stdin(Stdio::null())
            .stdout(Stdio::null())
            .stderr(Stdio::null());
        let status = cmd.status().context("running /usr/bin/say")?;
        if !status.success() {
            anyhow::bail!("`say` exited with {status}");
        }
        Ok(())
    }
}
