mod ui;

use std::time::Duration;

use anyhow::Result;
use clap::{Parser, Subcommand};
use nebulaos_core::{Command, run};
use tokio::sync::mpsc;

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
    },
    /// Export the latest session log.
    Export,
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
        Cmd::Start { minutes } => start(Duration::from_secs(minutes * 60)).await,
        Cmd::Export => export(),
    }
}

async fn start(total: Duration) -> Result<()> {
    print_banner(total);

    let (cmd_tx, cmd_rx) = mpsc::channel::<Command>(8);
    let events = run(cmd_rx, total);

    let ctrl_c = tokio::spawn(async move {
        let _ = tokio::signal::ctrl_c().await;
        let _ = cmd_tx.send(Command::End { completed: false }).await;
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
    println!("nebulaos — slice 1 skeleton");
    println!("session length: {mins} min  |  press Ctrl-C to end");
    println!();
}
