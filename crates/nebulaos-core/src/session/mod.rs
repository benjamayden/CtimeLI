use std::sync::Arc;
use std::time::{Duration, Instant};

use tokio::sync::mpsc;
use tokio::time::{self, MissedTickBehavior};
use tokio_stream::Stream;
use tokio_stream::wrappers::ReceiverStream;

use crate::partner::Partner;
use crate::vision::Attention;

pub const DEFAULT_TOTAL: Duration = Duration::from_secs(60 * 60);
const TICK: Duration = Duration::from_secs(1);
const EVENT_BUFFER: usize = 64;

/// Off-task accumulated since the last DriftSoftCheck before we nudge again.
/// PRD §4 Story 3: "soft verbal check-in, not an alarm". Cooldown is generous.
const DRIFT_NUDGE_AFTER: Duration = Duration::from_secs(60);
const DRIFT_NUDGE_COOLDOWN: Duration = Duration::from_secs(5 * 60);

#[derive(Debug, Clone)]
pub struct Session {
    pub goal: Option<String>,
    pub started: Instant,
    pub on_task: Duration,
    pub off_task: Duration,
    pub total: Duration,
    pub current_app: Option<String>,
    pub attention: Attention,
}

impl Session {
    pub fn new(total: Duration) -> Self {
        Self {
            goal: None,
            started: Instant::now(),
            on_task: Duration::ZERO,
            off_task: Duration::ZERO,
            total,
            current_app: None,
            attention: Attention::Unknown,
        }
    }
}

impl Default for Session {
    fn default() -> Self {
        Self::new(DEFAULT_TOTAL)
    }
}

#[derive(Debug, Clone)]
pub enum SessionEvent {
    Started { total: Duration },
    GoalDeclared(String),
    Tick {
        on_task: Duration,
        off_task: Duration,
        total: Duration,
    },
    FocusChanged { app: String, attention: Attention },
    PartnerSaid(String),
    DriftSoftCheck,
    Ended { completed: bool },
}

#[derive(Debug, Clone)]
pub enum Command {
    Declare(String),
    Focus { app: String, attention: Attention },
    Pause,
    Resume,
    End { completed: bool },
}

pub fn run(
    commands: mpsc::Receiver<Command>,
    total: Duration,
    partner: Option<Arc<dyn Partner>>,
) -> impl Stream<Item = SessionEvent> {
    let (tx, rx) = mpsc::channel(EVENT_BUFFER);
    tokio::spawn(run_loop(commands, total, partner, tx));
    ReceiverStream::new(rx)
}

async fn run_loop(
    mut commands: mpsc::Receiver<Command>,
    total: Duration,
    partner: Option<Arc<dyn Partner>>,
    tx: mpsc::Sender<SessionEvent>,
) {
    let mut session = Session::new(total);
    if tx.send(SessionEvent::Started { total }).await.is_err() {
        return;
    }

    let mut ticker = time::interval(TICK);
    ticker.set_missed_tick_behavior(MissedTickBehavior::Skip);
    let mut paused = false;
    let mut completed = false;
    let mut drift_since_last_nudge = Duration::ZERO;
    let mut last_nudge: Option<Instant> = None;

    loop {
        tokio::select! {
            cmd = commands.recv() => {
                match cmd {
                    Some(Command::Declare(goal)) => {
                        session.goal = Some(goal.clone());
                        if tx.send(SessionEvent::GoalDeclared(goal.clone())).await.is_err() {
                            break;
                        }
                        let welcome = match partner.as_ref() {
                            Some(p) => {
                                match p.respond(
                                    &format!("Starting a session. The goal is: {goal}."),
                                    "",
                                ).await {
                                    Ok(Some(line)) => Some(line),
                                    Ok(None) => None,
                                    Err(_) => Some(crate::partner::welcome(&goal)),
                                }
                            }
                            None => Some(crate::partner::welcome(&goal)),
                        };
                        if let Some(line) = welcome {
                            if tx.send(SessionEvent::PartnerSaid(line)).await.is_err() {
                                break;
                            }
                        }
                    }
                    Some(Command::Focus { app, attention }) => {
                        session.current_app = Some(app.clone());
                        session.attention = attention;
                        if attention != Attention::OffTask {
                            drift_since_last_nudge = Duration::ZERO;
                        }
                        if tx.send(SessionEvent::FocusChanged { app, attention }).await.is_err() {
                            break;
                        }
                    }
                    Some(Command::Pause) => paused = true,
                    Some(Command::Resume) => paused = false,
                    Some(Command::End { completed: c }) => {
                        completed = c;
                        break;
                    }
                    None => break,
                }
            }
            _ = ticker.tick() => {
                if paused {
                    session.off_task += TICK;
                } else {
                    match session.attention {
                        Attention::OffTask => {
                            session.off_task += TICK;
                            drift_since_last_nudge += TICK;
                        }
                        Attention::OnTask => session.on_task += TICK,
                        Attention::Unknown => session.on_task += TICK,
                    }
                }

                let evt = SessionEvent::Tick {
                    on_task: session.on_task,
                    off_task: session.off_task,
                    total: session.total,
                };
                if tx.send(evt).await.is_err() {
                    break;
                }

                let cooldown_ok = last_nudge
                    .map(|t| t.elapsed() >= DRIFT_NUDGE_COOLDOWN)
                    .unwrap_or(true);
                if drift_since_last_nudge >= DRIFT_NUDGE_AFTER && cooldown_ok {
                    drift_since_last_nudge = Duration::ZERO;
                    last_nudge = Some(Instant::now());
                    if tx.send(SessionEvent::DriftSoftCheck).await.is_err() {
                        break;
                    }
                    if let Some(p) = partner.as_ref() {
                        let goal = session.goal.as_deref().unwrap_or("the task");
                        let utterance = match session.current_app.as_deref() {
                            Some(app) => format!("They've been on {app} for a bit. Goal is {goal}."),
                            None => format!("They've drifted. Goal is {goal}."),
                        };
                        if let Ok(Some(line)) = p.respond(&utterance, "").await {
                            if tx.send(SessionEvent::PartnerSaid(line)).await.is_err() {
                                break;
                            }
                        }
                    }
                }

                if session.on_task + session.off_task >= session.total {
                    break;
                }
            }
        }
    }

    let _ = tx.send(SessionEvent::Ended { completed }).await;
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::partner::Partner;
    use anyhow::Result;
    use async_trait::async_trait;
    use futures::StreamExt;
    use std::sync::atomic::{AtomicUsize, Ordering};

    struct FixedPartner {
        line: String,
        calls: Arc<AtomicUsize>,
    }

    #[async_trait]
    impl Partner for FixedPartner {
        async fn respond(&self, _u: &str, _c: &str) -> Result<Option<String>> {
            self.calls.fetch_add(1, Ordering::SeqCst);
            Ok(Some(self.line.clone()))
        }
    }

    #[test]
    fn session_new_zeroes_counters() {
        let s = Session::new(Duration::from_secs(10));
        assert!(s.goal.is_none());
        assert_eq!(s.on_task, Duration::ZERO);
        assert_eq!(s.off_task, Duration::ZERO);
        assert_eq!(s.total, Duration::from_secs(10));
        assert_eq!(s.attention, Attention::Unknown);
    }

    #[tokio::test]
    async fn declare_emits_goal_then_stub_welcome() {
        let (tx, rx) = mpsc::channel(4);
        let mut stream = Box::pin(run(rx, Duration::from_secs(60), None));

        tx.send(Command::Declare("the copy".into())).await.unwrap();
        tx.send(Command::End { completed: true }).await.unwrap();

        let mut saw_goal = false;
        let mut saw_welcome = false;
        while let Some(evt) = stream.next().await {
            match evt {
                SessionEvent::GoalDeclared(g) => {
                    assert_eq!(g, "the copy");
                    saw_goal = true;
                }
                SessionEvent::PartnerSaid(line) => {
                    assert!(line.contains("the copy"));
                    saw_welcome = true;
                }
                SessionEvent::Ended { .. } => break,
                _ => {}
            }
        }
        assert!(saw_goal);
        assert!(saw_welcome);
    }

    #[tokio::test]
    async fn declare_uses_partner_when_provided() {
        let calls = Arc::new(AtomicUsize::new(0));
        let partner = Arc::new(FixedPartner {
            line: "ok — let's go.".into(),
            calls: calls.clone(),
        }) as Arc<dyn Partner>;

        let (tx, rx) = mpsc::channel(4);
        let mut stream = Box::pin(run(rx, Duration::from_secs(60), Some(partner)));

        tx.send(Command::Declare("the copy".into())).await.unwrap();
        tx.send(Command::End { completed: true }).await.unwrap();

        let mut welcome = None;
        while let Some(evt) = stream.next().await {
            match evt {
                SessionEvent::PartnerSaid(l) => welcome = Some(l),
                SessionEvent::Ended { .. } => break,
                _ => {}
            }
        }
        assert_eq!(welcome.as_deref(), Some("ok — let's go."));
        assert_eq!(calls.load(Ordering::SeqCst), 1);
    }

    #[tokio::test]
    async fn focus_event_changes_attention() {
        let (tx, rx) = mpsc::channel(4);
        let mut stream = Box::pin(run(rx, Duration::from_secs(60), None));

        tx.send(Command::Focus {
            app: "Twitter".into(),
            attention: Attention::OffTask,
        }).await.unwrap();
        tx.send(Command::End { completed: false }).await.unwrap();

        let mut focus_app = None;
        while let Some(evt) = stream.next().await {
            match evt {
                SessionEvent::FocusChanged { app, attention } => {
                    focus_app = Some((app, attention));
                }
                SessionEvent::Ended { .. } => break,
                _ => {}
            }
        }
        assert_eq!(
            focus_app.as_ref().map(|(a, b)| (a.as_str(), *b)),
            Some(("Twitter", Attention::OffTask))
        );
    }

    #[tokio::test]
    async fn run_emits_started_then_ended_on_end_command() {
        let (tx, rx) = mpsc::channel(4);
        let mut stream = Box::pin(run(rx, Duration::from_secs(60), None));
        tx.send(Command::End { completed: true }).await.unwrap();

        let first = stream.next().await.expect("started event");
        assert!(matches!(first, SessionEvent::Started { .. }));

        let last = loop {
            match stream.next().await {
                Some(SessionEvent::Ended { completed }) => break completed,
                Some(_) => continue,
                None => panic!("stream ended before Ended event"),
            }
        };
        assert!(last);
    }
}
