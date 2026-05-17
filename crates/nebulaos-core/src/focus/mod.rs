//! macOS app/tab focus events. PRD §4 Story 3: 1 frame per focus change + 5min heartbeat. Slice 4.

use anyhow::Result;

#[derive(Debug, Clone)]
pub struct FocusEvent {
    pub app: String,
    pub title: Option<String>,
}

pub trait FocusSource: Send + Sync {
    fn poll(&mut self) -> Result<Option<FocusEvent>>;
}
