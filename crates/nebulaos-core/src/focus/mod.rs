//! macOS app/tab focus events. PRD §4 Story 3: 1 frame per focus change +
//! 5min heartbeat.
//!
//! ## Status
//!
//! Slice 4-mac (TODO): wire `NSWorkspace.notificationCenter`'s
//! `NSWorkspaceDidActivateApplicationNotification` to push `FocusEvent` into
//! the session's `Command::Focus` channel. Use the `Vision` classifier to
//! turn the focused-app name into an `Attention`.
//!
//! Today the CLI sends a single `Command::Focus { app: "(unknown)",
//! attention: OnTask }` at session start so the tick loop runs.

use anyhow::Result;

#[derive(Debug, Clone)]
pub struct FocusEvent {
    pub app: String,
    pub title: Option<String>,
}

pub trait FocusSource: Send + Sync {
    fn poll(&mut self) -> Result<Option<FocusEvent>>;
}
