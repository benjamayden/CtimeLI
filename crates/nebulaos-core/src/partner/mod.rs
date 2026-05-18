//! Thinking partner. PRD §5/§8: Hermes via Ollama, voice spec, restraint. Slice 3.

use anyhow::Result;

pub trait Partner: Send + Sync {
    fn respond(&self, user_utterance: &str, context: &str) -> Result<Option<String>>;
}

/// Stub welcome line emitted after the user declares a goal. Slice 3 replaces
/// this with a Hermes call seeded by the voice spec (PRD §8).
pub fn welcome(goal: &str) -> String {
    let trimmed = goal.trim();
    if trimmed.is_empty() {
        "ok — what are we doing?".into()
    } else {
        format!("ok — on the {trimmed}.")
    }
}
