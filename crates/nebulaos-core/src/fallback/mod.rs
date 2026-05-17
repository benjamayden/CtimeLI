//! Claude API fallback. PRD §5/§6: text summaries only, no raw audio or screenshots. Slice 6.

use anyhow::Result;

pub trait Fallback: Send + Sync {
    fn reason(&self, summary: &str) -> Result<String>;
}
