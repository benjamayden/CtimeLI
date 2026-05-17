//! Thinking partner. PRD §5/§8: Hermes via Ollama, voice spec, restraint. Slice 3.

use anyhow::Result;

pub trait Partner: Send + Sync {
    fn respond(&self, user_utterance: &str, context: &str) -> Result<Option<String>>;
}
