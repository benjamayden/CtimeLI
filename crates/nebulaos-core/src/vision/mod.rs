//! Screen capture + attention classifier. PRD §4 Story 3 / §6 Candle. Slice 4.

use anyhow::Result;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Attention {
    OnTask,
    OffTask,
    Unknown,
}

pub trait Vision: Send + Sync {
    fn snapshot(&self) -> Result<Attention>;
}
