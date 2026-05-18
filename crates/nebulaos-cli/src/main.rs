mod prompt;
mod ui;

use std::path::PathBuf;
use std::sync::Arc;
use std::time::Duration;

use anyhow::{Context, Result};
use clap::{Parser, Subcommand};
use nebulaos_core::fallback::{ClaudeFallback, Fallback};
use nebulaos_core::log::{JsonlSessionLog, SessionSummary, export_latest};
use nebulaos_core::partner::{OllamaPartner, Partner};
use nebulaos_core::rag::{JsonlRag, Rag};
use nebulaos_core::vision::Attention;
use nebulaos_core::{Command, paths, run};
use tokio::sync::mpsc;

const DEFAULT_OLLAMA_URL: &str = "http://localhost:11434";
const DEFAULT_MODEL: &str = "hermes3:8b";

#[derive(Parser)]
#[command(name = "nebulaos", version, about = "Calm the nebulous chaos.")]
struct Cli {
    #[command(subcommand)]
    command: Cmd,
}

#[derive(Subcommand)]
enum Cmd {
    /// Start a session.
    Start {
        /// Session length in minutes.
        #[arg(long, default_value_t = 60)]
        minutes: u64,
        /// Skip the goal prompt (declare the goal inline).
        #[arg(long)]
        goal: Option<String>,
        /// Use the Ollama partner for the welcome and drift nudges.
        #[arg(long)]
        ollama: bool,
        /// Ollama base URL.
        #[arg(long, default_value = DEFAULT_OLLAMA_URL)]
        ollama_url: String,
        /// Model tag.
        #[arg(long, default_value = DEFAULT_MODEL)]
        model: String,
    },
    /// Export the latest session as clean text.
    Export,
    /// One-shot chat with the partner via local Ollama.
    Chat {
        prompt: String,
        #[arg(long, default_value = "")]
        context: String,
        #[arg(long, default_value = DEFAULT_OLLAMA_URL)]
        ollama_url: String,
        #[arg(long, default_value = DEFAULT_MODEL)]
        model: String,
    },
    /// Ingest a text file into the local RAG store.
    Ingest {
        file: PathBuf,
        /// Override the source label (defaults to the filename).
        #[arg(long)]
        source: Option<String>,
    },
    /// Recall the top matches for a query from the RAG store.
    Recall {
        query: String,
        #[arg(long, default_value_t = 5)]
        k: usize,
    },
    /// One-shot Claude fallback (text summary in, sharp line out).
    Fallback {
        summary: String,
        /// Override the default model.
        #[arg(long)]
        model: Option<String>,
    },
}

#[tokio::main]
async fn main() -> Result<()> {
    tracing_subscriber::fmt()
        .with_env_filter(
            tracing_subscriber::EnvFilter::try_from_default_env()
                .unwrap_or_else(|_| "warn,nebulaos_cli=info,nebulaos_core=info".into()),
        )
        .with_target(false)
        .init();

    let cli = Cli::parse();
    match cli.command {
        Cmd::Start { minutes, goal, ollama, ollama_url, model } => {
            let partner = if ollama {
                Some(Arc::new(OllamaPartner::new(ollama_url, model)?) as Arc<dyn Partner>)
            } else {
                None
            };
            start(Duration::from_secs(minutes * 60), goal, partner).await
        }
        Cmd::Export => export(),
        Cmd::Chat { prompt, context, ollama_url, model } => chat(prompt, context, ollama_url, model).await,
        Cmd::Ingest { file, source } => ingest(file, source),
        Cmd::Recall { query, k } => recall(query, k),
        Cmd::Fallback { summary, model } => fallback(summary, model).await,
    }
}

async fn chat(prompt: String, context: String, ollama_url: String, model: String) -> Result<()> {
    let partner = OllamaPartner::new(ollama_url, model)?;
    match partner.respond(&prompt, &context).await {
        Ok(Some(line)) => println!("{line}"),
        Ok(None) => println!("(silence)"),
        Err(e) => {
            eprintln!("partner unreachable: {e}");
            std::process::exit(2);
        }
    }
    Ok(())
}

async fn start(
    total: Duration,
    goal_arg: Option<String>,
    partner: Option<Arc<dyn Partner>>,
) -> Result<()> {
    print_banner(total);

    let goal = match goal_arg {
        Some(g) => g,
        None => prompt::declare_goal()?,
    };

    let sessions_dir = paths::sessions_dir()?;
    let session_id = paths::new_session_id();
    let mut log = JsonlSessionLog::new(&sessions_dir, &session_id)?;
    println!("logging to {}", log.path().display());
    println!();

    let (cmd_tx, cmd_rx) = mpsc::channel::<Command>(8);
    let events = run(cmd_rx, total, partner);

    cmd_tx.send(Command::Declare(goal)).await.ok();
    cmd_tx.send(Command::Focus {
        app: "(unknown)".into(),
        attention: Attention::OnTask,
    }).await.ok();

    let cmd_tx_end = cmd_tx.clone();
    let ctrl_c = tokio::spawn(async move {
        let _ = tokio::signal::ctrl_c().await;
        let _ = cmd_tx_end.send(Command::End { completed: false }).await;
    });

    ui::render(events, total, &mut log).await?;
    ctrl_c.abort();
    Ok(())
}

fn export() -> Result<()> {
    let dir = paths::sessions_dir()?;
    match export_latest(&dir) {
        Ok((path, summary)) => {
            println!("# nebulaos session — {}", path.display());
            print_summary(&summary);
            Ok(())
        }
        Err(e) => {
            eprintln!("no session to export: {e}");
            std::process::exit(2);
        }
    }
}

fn print_summary(s: &SessionSummary) {
    let total = s.on_task + s.off_task;
    let pct = if total.as_secs() > 0 {
        (s.on_task.as_secs() * 100) / total.as_secs()
    } else {
        0
    };
    println!();
    println!("goal:     {}", s.goal.as_deref().unwrap_or("(not declared)"));
    println!("on-task:  {}m {}s", s.on_task.as_secs() / 60, s.on_task.as_secs() % 60);
    println!("off-task: {}m {}s", s.off_task.as_secs() / 60, s.off_task.as_secs() % 60);
    println!("ratio:    {pct}% on-task");
    println!("drift:    {} soft check-ins", s.drift_events);
    match s.completed {
        Some(true) => println!("status:   done."),
        Some(false) => println!("status:   ended early."),
        None => println!("status:   (interrupted before end event)"),
    }
    if !s.partner_lines.is_empty() {
        println!();
        println!("partner said:");
        for line in &s.partner_lines {
            println!("  - {line}");
        }
    }
}

fn ingest(path: PathBuf, source: Option<String>) -> Result<()> {
    let text = std::fs::read_to_string(&path)
        .with_context(|| format!("read {}", path.display()))?;
    let source = source.unwrap_or_else(|| {
        path.file_name()
            .map(|s| s.to_string_lossy().into_owned())
            .unwrap_or_else(|| path.display().to_string())
    });
    let mut rag = JsonlRag::open(paths::rag_dir()?)?;
    rag.ingest(&source, &text)?;
    println!("ingested {} into {}", source, rag.dir().display());
    Ok(())
}

fn recall(query: String, k: usize) -> Result<()> {
    let rag = JsonlRag::open(paths::rag_dir()?)?;
    let hits = rag.query(&query, k)?;
    if hits.is_empty() {
        println!("(no matches)");
        return Ok(());
    }
    for hit in hits {
        println!("--- {}", hit.source);
        println!("{}", hit.snippet);
        println!();
    }
    Ok(())
}

async fn fallback(summary: String, model: Option<String>) -> Result<()> {
    let key = std::env::var("ANTHROPIC_API_KEY").context("ANTHROPIC_API_KEY not set")?;
    let client = match model {
        Some(m) => ClaudeFallback::with_model(key, m)?,
        None => ClaudeFallback::new(key)?,
    };
    match client.reason(&summary).await {
        Ok(line) => {
            println!("{line}");
            Ok(())
        }
        Err(e) => {
            eprintln!("fallback failed: {e}");
            std::process::exit(2);
        }
    }
}

fn print_banner(total: Duration) {
    let mins = total.as_secs() / 60;
    println!("nebulaos");
    println!("session length: {mins} min  |  press Ctrl-C to end");
    println!();
}
