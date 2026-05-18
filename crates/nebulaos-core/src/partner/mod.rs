//! Thinking partner. PRD §5/§8: Hermes via Ollama, voice spec, restraint.

mod ollama;
mod prompt;

pub use ollama::OllamaPartner;
pub use prompt::SYSTEM_PROMPT;

use anyhow::Result;

#[async_trait::async_trait]
pub trait Partner: Send + Sync {
    /// Returns Some(line) when the partner has something worth saying, None for silence.
    async fn respond(&self, user_utterance: &str, context: &str) -> Result<Option<String>>;
}

/// Stub welcome line emitted after the user declares a goal. Slice 3b replaces
/// this with a real OllamaPartner call inside the session loop.
pub fn welcome(goal: &str) -> String {
    let trimmed = goal.trim();
    if trimmed.is_empty() {
        "ok — what are we doing?".into()
    } else {
        format!("ok — on the {trimmed}.")
    }
}
