//! Project RAG + user model. PRD §5.
//!
//! Slice 5 ships a file-backed JSONL store: one append-only line per ingested
//! chunk, substring query. Slice 5b swaps the storage for LanceDB without
//! changing the `Rag` trait or the file layout for legacy reads.

mod jsonl;

pub use jsonl::JsonlRag;

use anyhow::Result;

pub trait Rag: Send + Sync {
    fn ingest(&mut self, source: &str, text: &str) -> Result<()>;
    fn query(&self, prompt: &str, k: usize) -> Result<Vec<RagHit>>;
    fn write_reflection(&mut self, reflection: &str) -> Result<()>;
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct RagHit {
    pub source: String,
    pub snippet: String,
}
