use std::fs::{self, File, OpenOptions};
use std::io::{BufRead, BufReader, Write};
use std::path::{Path, PathBuf};
use std::time::{SystemTime, UNIX_EPOCH};

use anyhow::{Context, Result};
use serde::{Deserialize, Serialize};

use super::{Rag, RagHit};

const CHUNKS_FILE: &str = "chunks.jsonl";
const REFLECTIONS_FILE: &str = "reflections.jsonl";
/// Lines longer than this get split on paragraph breaks before ingest.
const CHUNK_MAX_CHARS: usize = 600;

#[derive(Debug, Serialize, Deserialize)]
struct Chunk {
    source: String,
    text: String,
    ingested_at: u64,
}

#[derive(Debug, Serialize, Deserialize)]
struct Reflection {
    text: String,
    written_at: u64,
}

pub struct JsonlRag {
    dir: PathBuf,
}

impl JsonlRag {
    pub fn open(dir: impl Into<PathBuf>) -> Result<Self> {
        let dir = dir.into();
        fs::create_dir_all(&dir).with_context(|| format!("create rag dir {}", dir.display()))?;
        Ok(Self { dir })
    }

    fn chunks_path(&self) -> PathBuf {
        self.dir.join(CHUNKS_FILE)
    }

    fn reflections_path(&self) -> PathBuf {
        self.dir.join(REFLECTIONS_FILE)
    }

    pub fn dir(&self) -> &Path {
        &self.dir
    }

    fn append(path: &Path, line: &str) -> Result<()> {
        let mut f = OpenOptions::new()
            .create(true)
            .append(true)
            .open(path)
            .with_context(|| format!("open {}", path.display()))?;
        writeln!(f, "{line}")?;
        Ok(())
    }

    fn read_chunks(&self) -> Result<Vec<Chunk>> {
        let path = self.chunks_path();
        if !path.exists() {
            return Ok(vec![]);
        }
        let f = File::open(&path).with_context(|| format!("open {}", path.display()))?;
        let mut out = Vec::new();
        for line in BufReader::new(f).lines() {
            let line = line?;
            if line.trim().is_empty() {
                continue;
            }
            if let Ok(c) = serde_json::from_str::<Chunk>(&line) {
                out.push(c);
            }
        }
        Ok(out)
    }
}

impl Rag for JsonlRag {
    fn ingest(&mut self, source: &str, text: &str) -> Result<()> {
        let now = now_secs();
        for chunk in split_chunks(text) {
            let row = Chunk {
                source: source.to_string(),
                text: chunk,
                ingested_at: now,
            };
            let line = serde_json::to_string(&row)?;
            Self::append(&self.chunks_path(), &line)?;
        }
        Ok(())
    }

    fn query(&self, prompt: &str, k: usize) -> Result<Vec<RagHit>> {
        let needle = prompt.to_ascii_lowercase();
        let chunks = self.read_chunks()?;
        let mut scored: Vec<(usize, RagHit)> = chunks
            .into_iter()
            .filter_map(|c| {
                let hay = c.text.to_ascii_lowercase();
                if hay.contains(&needle) {
                    let score = needle
                        .split_whitespace()
                        .filter(|w| hay.contains(*w))
                        .count();
                    Some((
                        score,
                        RagHit {
                            source: c.source,
                            snippet: c.text,
                        },
                    ))
                } else {
                    None
                }
            })
            .collect();
        scored.sort_by(|a, b| b.0.cmp(&a.0));
        Ok(scored.into_iter().take(k).map(|(_, h)| h).collect())
    }

    fn write_reflection(&mut self, reflection: &str) -> Result<()> {
        let row = Reflection {
            text: reflection.to_string(),
            written_at: now_secs(),
        };
        Self::append(&self.reflections_path(), &serde_json::to_string(&row)?)
    }
}

fn now_secs() -> u64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_secs())
        .unwrap_or(0)
}

fn split_chunks(text: &str) -> Vec<String> {
    let mut out = Vec::new();
    for block in text.split("\n\n") {
        let trimmed = block.trim();
        if trimmed.is_empty() {
            continue;
        }
        if trimmed.chars().count() <= CHUNK_MAX_CHARS {
            out.push(trimmed.to_string());
            continue;
        }
        let mut current = String::new();
        for sentence in trimmed.split_inclusive(['.', '!', '?']) {
            if current.chars().count() + sentence.chars().count() > CHUNK_MAX_CHARS && !current.is_empty() {
                out.push(current.trim().to_string());
                current.clear();
            }
            current.push_str(sentence);
        }
        if !current.trim().is_empty() {
            out.push(current.trim().to_string());
        }
    }
    out
}

#[cfg(test)]
mod tests {
    use super::*;
    use tempfile::tempdir;

    #[test]
    fn ingest_then_query_returns_a_hit() {
        let dir = tempdir().unwrap();
        let mut rag = JsonlRag::open(dir.path()).unwrap();
        rag.ingest("brief.md", "The homepage hero should land on clarity, not flair.").unwrap();
        rag.ingest("notes.md", "Twitter is the enemy.").unwrap();

        let hits = rag.query("homepage hero", 5).unwrap();
        assert_eq!(hits.len(), 1);
        assert_eq!(hits[0].source, "brief.md");
        assert!(hits[0].snippet.contains("clarity"));
    }

    #[test]
    fn reflection_appends() {
        let dir = tempdir().unwrap();
        let mut rag = JsonlRag::open(dir.path()).unwrap();
        rag.write_reflection("Drift triggered by Slack at 23 min.").unwrap();
        let contents = fs::read_to_string(dir.path().join("reflections.jsonl")).unwrap();
        assert!(contents.contains("Slack"));
    }

    #[test]
    fn chunk_splitter_respects_max() {
        let long = "one.".repeat(400);
        let chunks = split_chunks(&long);
        assert!(chunks.iter().all(|c| c.chars().count() <= 700));
        assert!(chunks.len() > 1);
    }
}
