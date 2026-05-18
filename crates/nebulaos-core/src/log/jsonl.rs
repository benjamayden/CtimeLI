use std::fs::{self, File, OpenOptions};
use std::io::{BufRead, BufReader, Write};
use std::path::{Path, PathBuf};
use std::time::{Duration, SystemTime, UNIX_EPOCH};

use anyhow::{Context, Result, anyhow};
use serde::{Deserialize, Serialize};

use crate::SessionEvent;

#[derive(Debug, Serialize, Deserialize)]
#[serde(tag = "kind")]
enum LogEntry {
    Started { total_secs: u64, at: u64 },
    GoalDeclared { goal: String, at: u64 },
    Tick { on_task_secs: u64, off_task_secs: u64, at: u64 },
    FocusChanged { app: String, attention: String, at: u64 },
    PartnerSaid { text: String, at: u64 },
    DriftSoftCheck { at: u64 },
    Ended { completed: bool, at: u64 },
}

impl LogEntry {
    fn from_event(evt: &SessionEvent) -> Self {
        let at = now_secs();
        match evt {
            SessionEvent::Started { total } => LogEntry::Started { total_secs: total.as_secs(), at },
            SessionEvent::GoalDeclared(g) => LogEntry::GoalDeclared { goal: g.clone(), at },
            SessionEvent::Tick { on_task, off_task, .. } => LogEntry::Tick {
                on_task_secs: on_task.as_secs(),
                off_task_secs: off_task.as_secs(),
                at,
            },
            SessionEvent::FocusChanged { app, attention } => LogEntry::FocusChanged {
                app: app.clone(),
                attention: format!("{attention:?}"),
                at,
            },
            SessionEvent::PartnerSaid(t) => LogEntry::PartnerSaid { text: t.clone(), at },
            SessionEvent::DriftSoftCheck => LogEntry::DriftSoftCheck { at },
            SessionEvent::Ended { completed } => LogEntry::Ended { completed: *completed, at },
        }
    }
}

/// Append-only JSONL session log. One file per session at
/// `<dir>/<id>.jsonl`. Tick events are downsampled — one row per `tick_every`
/// ticks — so a 60-min session is a small file.
pub struct JsonlSessionLog {
    path: PathBuf,
    tick_every: u32,
    tick_counter: u32,
}

impl JsonlSessionLog {
    pub fn new(dir: impl AsRef<Path>, id: &str) -> Result<Self> {
        fs::create_dir_all(dir.as_ref())
            .with_context(|| format!("create session log dir {}", dir.as_ref().display()))?;
        Ok(Self {
            path: dir.as_ref().join(format!("{id}.jsonl")),
            tick_every: 60,
            tick_counter: 0,
        })
    }

    pub fn path(&self) -> &Path {
        &self.path
    }

    pub fn record(&mut self, evt: &SessionEvent) -> Result<()> {
        if matches!(evt, SessionEvent::Tick { .. }) {
            self.tick_counter += 1;
            if !self.tick_counter.is_multiple_of(self.tick_every) {
                return Ok(());
            }
        }
        let entry = LogEntry::from_event(evt);
        let line = serde_json::to_string(&entry)?;
        let mut f = OpenOptions::new()
            .create(true)
            .append(true)
            .open(&self.path)
            .with_context(|| format!("open {}", self.path.display()))?;
        writeln!(f, "{line}")?;
        Ok(())
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct SessionSummary {
    pub goal: Option<String>,
    pub on_task: Duration,
    pub off_task: Duration,
    pub total: Duration,
    pub drift_events: u32,
    pub partner_lines: Vec<String>,
    pub completed: Option<bool>,
}

/// Read one session file and roll it up into a clean text-friendly summary.
pub fn summarize(path: &Path) -> Result<SessionSummary> {
    let f = File::open(path).with_context(|| format!("open {}", path.display()))?;
    let mut goal = None;
    let mut on_task = Duration::ZERO;
    let mut off_task = Duration::ZERO;
    let mut total = Duration::ZERO;
    let mut drift_events = 0u32;
    let mut partner_lines = Vec::new();
    let mut completed = None;

    for line in BufReader::new(f).lines() {
        let line = line?;
        if line.trim().is_empty() {
            continue;
        }
        let entry: LogEntry = match serde_json::from_str(&line) {
            Ok(e) => e,
            Err(_) => continue,
        };
        match entry {
            LogEntry::Started { total_secs, .. } => total = Duration::from_secs(total_secs),
            LogEntry::GoalDeclared { goal: g, .. } => goal = Some(g),
            LogEntry::Tick { on_task_secs, off_task_secs, .. } => {
                on_task = Duration::from_secs(on_task_secs);
                off_task = Duration::from_secs(off_task_secs);
            }
            LogEntry::DriftSoftCheck { .. } => drift_events += 1,
            LogEntry::PartnerSaid { text, .. } => partner_lines.push(text),
            LogEntry::Ended { completed: c, .. } => completed = Some(c),
            LogEntry::FocusChanged { .. } => {}
        }
    }

    Ok(SessionSummary {
        goal,
        on_task,
        off_task,
        total,
        drift_events,
        partner_lines,
        completed,
    })
}

/// Find the most recent session file in `dir` and summarize it.
pub fn export_latest(dir: &Path) -> Result<(PathBuf, SessionSummary)> {
    let path = latest_session(dir)?;
    let summary = summarize(&path)?;
    Ok((path, summary))
}

fn latest_session(dir: &Path) -> Result<PathBuf> {
    let mut best: Option<(SystemTime, PathBuf)> = None;
    for entry in fs::read_dir(dir).with_context(|| format!("read_dir {}", dir.display()))? {
        let entry = entry?;
        let path = entry.path();
        if path.extension().and_then(|s| s.to_str()) != Some("jsonl") {
            continue;
        }
        let mtime = entry.metadata()?.modified()?;
        if best.as_ref().is_none_or(|(t, _)| mtime > *t) {
            best = Some((mtime, path));
        }
    }
    best.map(|(_, p)| p).ok_or_else(|| anyhow!("no session files in {}", dir.display()))
}

fn now_secs() -> u64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_secs())
        .unwrap_or(0)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::vision::Attention;
    use tempfile::tempdir;

    #[test]
    fn records_and_summarises_a_session() {
        let dir = tempdir().unwrap();
        let mut log = JsonlSessionLog::new(dir.path(), "test").unwrap();
        log.tick_every = 1;

        log.record(&SessionEvent::Started { total: Duration::from_secs(60) }).unwrap();
        log.record(&SessionEvent::GoalDeclared("the copy".into())).unwrap();
        log.record(&SessionEvent::Tick {
            on_task: Duration::from_secs(30),
            off_task: Duration::from_secs(10),
            total: Duration::from_secs(60),
        }).unwrap();
        log.record(&SessionEvent::FocusChanged {
            app: "Twitter".into(),
            attention: Attention::OffTask,
        }).unwrap();
        log.record(&SessionEvent::DriftSoftCheck).unwrap();
        log.record(&SessionEvent::PartnerSaid("still on the copy?".into())).unwrap();
        log.record(&SessionEvent::Ended { completed: true }).unwrap();

        let summary = summarize(log.path()).unwrap();
        assert_eq!(summary.goal.as_deref(), Some("the copy"));
        assert_eq!(summary.on_task, Duration::from_secs(30));
        assert_eq!(summary.off_task, Duration::from_secs(10));
        assert_eq!(summary.drift_events, 1);
        assert_eq!(summary.partner_lines, vec!["still on the copy?"]);
        assert_eq!(summary.completed, Some(true));
    }

    #[test]
    fn ticks_downsample_by_default() {
        let dir = tempdir().unwrap();
        let mut log = JsonlSessionLog::new(dir.path(), "ds").unwrap();
        for i in 1..=180 {
            log.record(&SessionEvent::Tick {
                on_task: Duration::from_secs(i),
                off_task: Duration::ZERO,
                total: Duration::from_secs(3600),
            }).unwrap();
        }
        let contents = fs::read_to_string(log.path()).unwrap();
        // 180 ticks at every-60 → 3 lines.
        assert_eq!(contents.lines().count(), 3);
    }
}
