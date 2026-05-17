//! Paths, model selection, redaction rules. Wired up across slices.

use std::path::PathBuf;
use std::time::Duration;

#[derive(Debug, Clone)]
pub struct Config {
    pub data_dir: PathBuf,
    pub session_total: Duration,
    pub ollama_url: String,
    pub hermes_model: String,
}

impl Default for Config {
    fn default() -> Self {
        Self {
            data_dir: PathBuf::from(".nebulaos"),
            session_total: crate::session::DEFAULT_TOTAL,
            ollama_url: "http://localhost:11434".into(),
            hermes_model: "hermes3:8b".into(),
        }
    }
}
