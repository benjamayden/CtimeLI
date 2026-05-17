use std::time::{Duration, Instant};

use tokio::sync::mpsc;
use tokio::time::{self, MissedTickBehavior};
use tokio_stream::Stream;
use tokio_stream::wrappers::ReceiverStream;

pub const DEFAULT_TOTAL: Duration = Duration::from_secs(60 * 60);
const TICK: Duration = Duration::from_secs(1);
const EVENT_BUFFER: usize = 64;

#[derive(Debug, Clone)]
pub struct Session {
    pub goal: Option<String>,
    pub started: Instant,
    pub on_task: Duration,
    pub off_task: Duration,
    pub total: Duration,
}

impl Session {
    pub fn new(total: Duration) -> Self {
        Self {
            goal: None,
            started: Instant::now(),
            on_task: Duration::ZERO,
            off_task: Duration::ZERO,
            total,
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
    PartnerSaid(String),
    DriftSoftCheck,
    Ended { completed: bool },
}

#[derive(Debug, Clone)]
pub enum Command {
    Declare(String),
    Pause,
    Resume,
    End { completed: bool },
}

pub fn run(mut commands: mpsc::Receiver<Command>, total: Duration) -> impl Stream<Item = SessionEvent> {
    let (tx, rx) = mpsc::channel(EVENT_BUFFER);

    tokio::spawn(async move {
        let mut session = Session::new(total);
        if tx.send(SessionEvent::Started { total }).await.is_err() {
            return;
        }

        let mut ticker = time::interval(TICK);
        ticker.set_missed_tick_behavior(MissedTickBehavior::Skip);
        let mut paused = false;
        let mut completed = false;

        loop {
            tokio::select! {
                cmd = commands.recv() => {
                    match cmd {
                        Some(Command::Declare(goal)) => {
                            session.goal = Some(goal.clone());
                            if tx.send(SessionEvent::GoalDeclared(goal)).await.is_err() {
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
                    if !paused {
                        session.on_task += TICK;
                    } else {
                        session.off_task += TICK;
                    }
                    let evt = SessionEvent::Tick {
                        on_task: session.on_task,
                        off_task: session.off_task,
                        total: session.total,
                    };
                    if tx.send(evt).await.is_err() {
                        break;
                    }
                    if session.on_task + session.off_task >= session.total {
                        break;
                    }
                }
            }
        }

        let _ = tx.send(SessionEvent::Ended { completed }).await;
    });

    ReceiverStream::new(rx)
}

#[cfg(test)]
mod tests {
    use super::*;
    use futures::StreamExt;

    #[test]
    fn session_new_zeroes_counters() {
        let s = Session::new(Duration::from_secs(10));
        assert!(s.goal.is_none());
        assert_eq!(s.on_task, Duration::ZERO);
        assert_eq!(s.off_task, Duration::ZERO);
        assert_eq!(s.total, Duration::from_secs(10));
    }

    #[tokio::test]
    async fn run_emits_started_then_ended_on_end_command() {
        let (tx, rx) = mpsc::channel(4);
        let mut stream = Box::pin(run(rx, Duration::from_secs(60)));
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
