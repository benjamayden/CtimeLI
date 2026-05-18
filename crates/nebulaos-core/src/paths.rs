//! Filesystem layout. Everything lives under one data dir so the user can
//! see and delete anything stored (PRD §5 memory promise).

use std::path::PathBuf;

use anyhow::{Context, Result};
use directories::ProjectDirs;

const QUALIFIER: &str = "io";
const ORG: &str = "lenniott";
const APP: &str = "nebulaos";

pub fn data_dir() -> Result<PathBuf> {
    if let Ok(override_) = std::env::var("NEBULAOS_DATA_DIR") {
        return Ok(PathBuf::from(override_));
    }
    let dirs = ProjectDirs::from(QUALIFIER, ORG, APP)
        .context("could not resolve a data directory for this OS")?;
    Ok(dirs.data_dir().to_path_buf())
}

pub fn sessions_dir() -> Result<PathBuf> {
    Ok(data_dir()?.join("sessions"))
}

pub fn rag_dir() -> Result<PathBuf> {
    Ok(data_dir()?.join("rag"))
}

pub fn new_session_id() -> String {
    use std::time::{SystemTime, UNIX_EPOCH};
    let ts = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_secs())
        .unwrap_or(0);
    format!("session-{ts}")
}
