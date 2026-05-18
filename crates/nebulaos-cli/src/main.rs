mod prompt;
mod ui;

use std::time::Duration;

use anyhow::Result;
use clap::{Parser, Subcommand};
use nebulaos_core::partner::{OllamaPartner, Partner};
use nebulaos_core::{Command, run};
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
    },
    /// Export the latest session log.
    Export,
    /// One-shot chat with the partner via local Ollama.
    Chat {
        /// What you want to say.
        prompt: String,
        /// Optional context (e.g. current goal).
        #[arg(long, default_value = "")]
        context: String,
        /// Ollama base URL.
        #[arg(long, default_value = DEFAULT_OLLAMA_URL)]
        ollama_url: String,
        /// Model tag.
        #[arg(long, default_value = DEFAULT_MODEL)]
        model: String,
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
        Cmd::Start { minutes, goal } => start(Duration::from_secs(minutes * 60), goal).await,
        Cmd::Export => export(),
        Cmd::Chat { prompt, context, ollama_url, model } => chat(prompt, context, ollama_url, model).await,
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

async fn start(total: Duration, goal_arg: Option<String>) -> Result<()> {
    print_banner(total);

    let goal = match goal_arg {
        Some(g) => g,
        None => prompt::declare_goal()?,
    };

    let (cmd_tx, cmd_rx) = mpsc::channel::<Command>(8);
    let events = run(cmd_rx, total);

    cmd_tx.send(Command::Declare(goal)).await.ok();

    let cmd_tx_end = cmd_tx.clone();
    let ctrl_c = tokio::spawn(async move {
        let _ = tokio::signal::ctrl_c().await;
        let _ = cmd_tx_end.send(Command::End { completed: false }).await;
    });

    ui::render(events, total).await?;
    ctrl_c.abort();
    Ok(())
}

fn export() -> Result<()> {
    println!("(slice 1 stub) session log export will land at ~/.nebulaos/sessions/<id>.txt");
    Ok(())
}

fn print_banner(total: Duration) {
    let mins = total.as_secs() / 60;
    println!("nebulaos");
    println!("session length: {mins} min  |  press Ctrl-C to end");
    println!();
}
