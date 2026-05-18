//! Claude API fallback. PRD §5/§6: text summaries only, no raw audio or
//! screenshots ever leave the device. Used for the hard reasoning moments
//! where on-device Hermes isn't sharp enough.

mod claude;

pub use claude::ClaudeFallback;

use anyhow::Result;
use async_trait::async_trait;

#[async_trait]
pub trait Fallback: Send + Sync {
    async fn reason(&self, summary: &str) -> Result<String>;
}
