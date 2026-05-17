//! Project RAG + user model. PRD §5: LanceDB embedded. Slice 5.

use anyhow::Result;

pub trait Rag: Send + Sync {
    fn ingest(&mut self, source: &str, text: &str) -> Result<()>;
    fn query(&self, prompt: &str, k: usize) -> Result<Vec<String>>;
    fn write_reflection(&mut self, reflection: &str) -> Result<()>;
}
