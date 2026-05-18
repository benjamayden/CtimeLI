use std::sync::Arc;
use std::time::Duration;

use anyhow::Result;
use futures::{Stream, StreamExt};
use indicatif::{ProgressBar, ProgressStyle};
use nebulaos_core::SessionEvent;
use nebulaos_core::audio::AudioOutput;
use nebulaos_core::log::JsonlSessionLog;

pub async fn render<S>(
    events: S,
    total: Duration,
    log: &mut JsonlSessionLog,
    speaker: Option<Arc<dyn AudioOutput>>,
) -> Result<()>
where
    S: Stream<Item = SessionEvent>,
{
    let bar = ProgressBar::new(total.as_secs());
    bar.set_style(
        ProgressStyle::with_template("{bar:40.cyan/blue} {pos}s / {len}s on-task  {msg}")
            .expect("valid template")
            .progress_chars("█▉▊▋▌▍▎▏ "),
    );

    tokio::pin!(events);
    while let Some(evt) = events.next().await {
        if let Err(e) = log.record(&evt) {
            tracing::warn!(error = ?e, "session log write failed");
        }
        match &evt {
            SessionEvent::Started { total } => {
                bar.set_length(total.as_secs());
            }
            SessionEvent::GoalDeclared(goal) => {
                bar.set_message(format!("goal: {goal}"));
            }
            SessionEvent::Tick { on_task, .. } => {
                bar.set_position(on_task.as_secs());
            }
            SessionEvent::FocusChanged { app, attention } => {
                tracing::debug!(?attention, app, "focus changed");
            }
            SessionEvent::PartnerSaid(line) => {
                bar.println(format!("  ← {line}"));
                if let Some(s) = speaker.as_ref() {
                    speak_in_background(s.clone(), line.clone());
                }
            }
            SessionEvent::DriftSoftCheck => {
                tracing::debug!("drift soft check fired");
            }
            SessionEvent::Ended { completed } => {
                bar.finish_with_message(if *completed { "done." } else { "ended." });
                break;
            }
        }
    }
    Ok(())
}

fn speak_in_background(speaker: Arc<dyn AudioOutput>, line: String) {
    tokio::task::spawn_blocking(move || {
        if let Err(e) = speaker.speak(&line) {
            tracing::warn!(error = ?e, "tts failed");
        }
    });
}
