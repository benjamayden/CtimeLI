//! macOS app-focus listener via NSWorkspace.
//!
//! Polls `NSWorkspace.sharedWorkspace.frontmostApplication` every 500ms and
//! emits a `FocusEvent` whenever it changes. Polling — rather than KVO or
//! the `NSWorkspaceDidActivateApplicationNotification` distributed
//! notification — keeps the FFI tiny and avoids needing an `NSRunLoop`
//! on the listening thread. The session machine's tick is 1s, so 500ms
//! polling is plenty.
//!
//! Permissions: this uses public, non-sandboxed AppKit APIs. No
//! Accessibility entitlement required for the frontmost-app name. Window
//! titles (deeper info) would need Accessibility — skipping for now.

use std::sync::Arc;
use std::time::Duration;

use anyhow::{Context, Result};
use objc2::rc::Retained;
use objc2_app_kit::{NSRunningApplication, NSWorkspace};
use objc2_foundation::NSString;
use tokio::sync::mpsc;
use tokio::task::JoinHandle;
use tokio::time;

use super::FocusEvent;

const POLL_INTERVAL: Duration = Duration::from_millis(500);

/// Spawn a polling task that emits `FocusEvent` every time the frontmost
/// application changes. Returns the receiver and the join handle so the
/// caller can shut it down cleanly.
pub fn spawn_focus_listener() -> Result<(mpsc::Receiver<FocusEvent>, JoinHandle<()>)> {
    let (tx, rx) = mpsc::channel(32);
    let handle = tokio::spawn(async move {
        let mut current: Option<String> = None;
        let mut ticker = time::interval(POLL_INTERVAL);
        loop {
            ticker.tick().await;
            match frontmost_app_name() {
                Ok(Some(name)) => {
                    if current.as_deref() != Some(name.as_str()) {
                        current = Some(name.clone());
                        let event = FocusEvent { app: name, title: None };
                        if tx.send(event).await.is_err() {
                            break;
                        }
                    }
                }
                Ok(None) => continue,
                Err(e) => {
                    tracing::warn!(error = ?e, "frontmost_app_name failed");
                    continue;
                }
            }
        }
    });
    Ok((rx, handle))
}

/// One-shot read: returns the name of the frontmost application, or None
/// if AppKit reports no active app.
pub fn frontmost_app_name() -> Result<Option<String>> {
    // Safety: NSWorkspace and NSRunningApplication APIs are documented to
    // return Option-typed handles; objc2 wraps that into Retained<T>.
    unsafe {
        let workspace: Retained<NSWorkspace> = NSWorkspace::sharedWorkspace();
        let app: Option<Retained<NSRunningApplication>> = workspace.frontmostApplication();
        let Some(app) = app else { return Ok(None) };
        let name: Option<Retained<NSString>> = app.localizedName();
        let Some(name) = name else { return Ok(None) };
        Ok(Some(name.to_string()))
    }
}

/// A `FocusSource` that wraps the polling listener. Kept for completeness;
/// most callers will use `spawn_focus_listener()` directly and feed events
/// into `Command::Focus`.
pub struct NSWorkspaceFocusSource {
    rx: Arc<tokio::sync::Mutex<mpsc::Receiver<FocusEvent>>>,
    _handle: JoinHandle<()>,
}

impl NSWorkspaceFocusSource {
    pub fn new() -> Result<Self> {
        let (rx, handle) = spawn_focus_listener().context("spawn NSWorkspace listener")?;
        Ok(Self {
            rx: Arc::new(tokio::sync::Mutex::new(rx)),
            _handle: handle,
        })
    }

    pub async fn recv(&self) -> Option<FocusEvent> {
        self.rx.lock().await.recv().await
    }
}

