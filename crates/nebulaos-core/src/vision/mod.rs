//! Screen capture + attention classifier. PRD §4 Story 3 / §6 Candle. Slice 4.

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
