//! Goal declaration prompt. Slice 2: stdin line. Slice 2b swaps this for
//! cpal mic capture + Whisper Tiny — same return contract.

use std::io::{self, BufRead, Write};

use anyhow::Result;

pub fn declare_goal() -> Result<String> {
    let stdout = io::stdout();
    let mut out = stdout.lock();
    write!(out, "what are we doing? ")?;
    out.flush()?;

    let stdin = io::stdin();
    let mut line = String::new();
    stdin.lock().read_line(&mut line)?;
    let trimmed = line.trim().to_string();
    Ok(trimmed)
}
