//! Screen capture + attention classifier. PRD §4 Story 3 / §6 Candle.
//!
//! For concept validation we ship a `WorkspaceClassifier`: the user declares
//! which app names count as on-task workspaces at session start; everything
//! else is off-task. The full Candle vision classifier is a later upgrade —
//! same `Attention` output, swapped in behind the same call site.

use anyhow::Result;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Attention {
    OnTask,
    OffTask,
    Unknown,
}

impl Attention {
    pub fn parse(s: &str) -> Option<Self> {
        match s.to_ascii_lowercase().as_str() {
            "on" | "on-task" | "ontask" => Some(Attention::OnTask),
            "off" | "off-task" | "offtask" => Some(Attention::OffTask),
            "unknown" | "?" => Some(Attention::Unknown),
            _ => None,
        }
    }
}

pub trait Vision: Send + Sync {
    fn snapshot(&self) -> Result<Attention>;
}

/// Name-based classifier: an app counts as on-task if its name (case-insensitive,
/// trimmed) is in the user-declared workspace list. Everything else is off-task.
#[derive(Debug, Clone)]
pub struct WorkspaceClassifier {
    workspaces: Vec<String>,
}

impl WorkspaceClassifier {
    pub fn new<I, S>(workspaces: I) -> Self
    where
        I: IntoIterator<Item = S>,
        S: Into<String>,
    {
        Self {
            workspaces: workspaces
                .into_iter()
                .map(|s| s.into().trim().to_ascii_lowercase())
                .filter(|s| !s.is_empty())
                .collect(),
        }
    }

    pub fn is_empty(&self) -> bool {
        self.workspaces.is_empty()
    }

    pub fn classify(&self, app_name: &str) -> Attention {
        if self.workspaces.is_empty() {
            return Attention::Unknown;
        }
        let needle = app_name.trim().to_ascii_lowercase();
        if self.workspaces.iter().any(|w| needle.contains(w)) {
            Attention::OnTask
        } else {
            Attention::OffTask
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn empty_workspaces_returns_unknown() {
        let c = WorkspaceClassifier::new(Vec::<String>::new());
        assert_eq!(c.classify("Twitter"), Attention::Unknown);
    }

    #[test]
    fn declared_workspaces_are_on_task() {
        let c = WorkspaceClassifier::new(["figma", "Notion"]);
        assert_eq!(c.classify("Figma"), Attention::OnTask);
        assert_eq!(c.classify("Notion"), Attention::OnTask);
        assert_eq!(c.classify("Twitter"), Attention::OffTask);
    }

    #[test]
    fn partial_match_counts_as_on_task() {
        // "Google Chrome" containing the declared "chrome" still on-task.
        let c = WorkspaceClassifier::new(["chrome"]);
        assert_eq!(c.classify("Google Chrome"), Attention::OnTask);
    }
}

