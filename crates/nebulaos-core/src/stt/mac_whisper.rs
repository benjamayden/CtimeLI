//! Whisper Tiny via `whisper-rs` on macOS.
//!
//! Loads a GGML model file (e.g. `ggml-tiny.bin`) and transcribes 16 kHz
//! mono i16 PCM. Build requires `cmake` and Xcode command-line tools:
//!
//! ```sh
//! brew install cmake
//! xcode-select --install
//! ```
//!
//! And the model file:
//!
//! ```sh
//! mkdir -p ~/.nebulaos/models
//! curl -L -o ~/.nebulaos/models/ggml-tiny.bin \
//!   https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-tiny.bin
//! ```

use std::path::{Path, PathBuf};

use anyhow::{Context, Result, anyhow};
use whisper_rs::{FullParams, SamplingStrategy, WhisperContext, WhisperContextParameters};

use crate::stt::SpeechToText;

const TARGET_SAMPLE_RATE: u32 = 16_000;

pub struct WhisperTranscriber {
    ctx: WhisperContext,
    language: Option<String>,
}

impl WhisperTranscriber {
    pub fn open(model_path: impl AsRef<Path>) -> Result<Self> {
        let path = model_path.as_ref();
        if !path.exists() {
            return Err(anyhow!(
                "whisper model not found at {}. Download with: \
                 curl -L -o {} \
                 https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-tiny.bin",
                path.display(),
                path.display(),
            ));
        }
        let ctx = WhisperContext::new_with_params(
            path.to_str().context("model path is not utf-8")?,
            WhisperContextParameters::default(),
        )
        .context("load whisper model")?;
        Ok(Self { ctx, language: Some("en".into()) })
    }

    pub fn with_language(mut self, lang: impl Into<String>) -> Self {
        self.language = Some(lang.into());
        self
    }

    pub fn default_model_path() -> PathBuf {
        crate::paths::data_dir()
            .unwrap_or_else(|_| PathBuf::from("."))
            .join("models")
            .join("ggml-tiny.bin")
    }
}

impl SpeechToText for WhisperTranscriber {
    fn transcribe(&self, pcm: &[i16]) -> Result<String> {
        if pcm.is_empty() {
            return Ok(String::new());
        }
        let mut audio = vec![0.0_f32; pcm.len()];
        whisper_rs::convert_integer_to_float_audio(pcm, &mut audio)
            .context("convert i16 → f32 for whisper")?;

        let mut state = self.ctx.create_state().context("create whisper state")?;
        let mut params = FullParams::new(SamplingStrategy::Greedy { best_of: 1 });
        params.set_print_progress(false);
        params.set_print_realtime(false);
        params.set_print_timestamps(false);
        params.set_single_segment(true);
        params.set_suppress_blank(true);
        if let Some(lang) = self.language.as_deref() {
            params.set_language(Some(lang));
        }

        state.full(params, &audio).context("whisper inference")?;

        let n = state.full_n_segments().context("count segments")?;
        let mut out = String::new();
        for i in 0..n {
            let seg = state
                .full_get_segment_text(i)
                .with_context(|| format!("read segment {i}"))?;
            out.push_str(&seg);
        }
        Ok(out.trim().to_string())
    }
}

#[allow(dead_code)]
fn assert_target_rate() {
    // Documentation: the mic capture resamples to TARGET_SAMPLE_RATE before
    // calling transcribe(). If you change one, change the other.
    let _ = TARGET_SAMPLE_RATE;
}
