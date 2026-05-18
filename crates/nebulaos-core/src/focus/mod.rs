//! macOS app/tab focus events. PRD §4 Story 3: a soft check-in when the
//! frontmost app stops being on-task for long enough.

use anyhow::Result;

#[cfg(target_os = "macos")]
mod mac_nsworkspace;

#[cfg(target_os = "macos")]
pub use mac_nsworkspace::{spawn_focus_listener, frontmost_app_name};

#[derive(Debug, Clone)]
pub struct FocusEvent {
    pub app: String,
    pub title: Option<String>,
}

pub trait FocusSource: Send + Sync {
    fn poll(&mut self) -> Result<Option<FocusEvent>>;
}

