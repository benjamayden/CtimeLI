//! Session log + export. PRD §4 Story 6. Slice 6.

use anyhow::Result;
use std::path::PathBuf;

pub trait SessionLog: Send + Sync {
    fn record(&mut self, line: &str) -> Result<()>;
    fn export(&self) -> Result<PathBuf>;
}
