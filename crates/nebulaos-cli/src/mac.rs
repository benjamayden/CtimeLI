//! macOS-only CLI plumbing: live mic goal capture, focus listener task,
//! `say` TTS, doctor checks.
//!
//! Compiled out on non-macOS targets.

#![cfg(target_os = "macos")]

use std::io::{self, Read, Write};
use std::path::PathBuf;
use std::sync::Arc;
use std::time::Duration;

use anyhow::{Context, Result};
use nebulaos_core::audio::{AudioOutput, MacMicCapture, SaySpeech};
use nebulaos_core::focus::spawn_focus_listener;
use nebulaos_core::stt::{SpeechToText, WhisperTranscriber};
use nebulaos_core::vision::WorkspaceClassifier;
use nebulaos_core::{Command, paths};
use tokio::sync::mpsc;
use tokio::task::{self, JoinHandle};

/// Push-to-talk goal declaration: prompt the user, capture until they press
/// Enter, transcribe with Whisper, return the text. Falls back to stdin if
/// the model file is missing.
pub fn declare_goal_voice() -> Result<String> {
    let model = WhisperTranscriber::default_model_path();
    if !model.exists() {
        eprintln!(
            "whisper model not found at {} — falling back to typed goal.",
            model.display()
        );
        eprintln!("run `nebulaos doctor` for the download command.");
        return crate::prompt::declare_goal();
    }

    println!("what are we doing? (press Enter to start recording, Enter again to stop)");
    wait_for_enter()?;
    println!("listening…");
    let handle = MacMicCapture::start().context("starting mic capture")?;
    wait_for_enter()?;
    let pcm = handle.stop()?;
    if pcm.is_empty() {
        eprintln!("(no audio captured — falling back to typed goal)");
        return crate::prompt::declare_goal();
    }
    println!("transcribing {} samples…", pcm.len());
    let stt = WhisperTranscriber::open(&model)?;
    let text = stt.transcribe(&pcm)?;
    println!("heard: {text}");
    Ok(text)
}

fn wait_for_enter() -> Result<()> {
    let mut byte = [0u8; 1];
    let _ = io::stdout().flush();
    io::stdin().read(&mut byte).context("reading stdin")?;
    Ok(())
}

/// Spawn the NSWorkspace focus listener. Each focus change becomes a
/// `Command::Focus` with attention classified by the user's declared
/// workspaces.
pub fn spawn_focus_relay(
    cmd_tx: mpsc::Sender<Command>,
    classifier: WorkspaceClassifier,
) -> Result<JoinHandle<()>> {
    let (mut rx, _listener) = spawn_focus_listener()?;
    // _listener is the inner polling task; it exits on its own when `rx` is
    // dropped (next send fails), so we just let it run as a daemon.
    drop(_listener);
    let handle = task::spawn(async move {
        while let Some(evt) = rx.recv().await {
            let attention = classifier.classify(&evt.app);
            let send = cmd_tx.send(Command::Focus {
                app: evt.app,
                attention,
            }).await;
            if send.is_err() {
                break;
            }
        }
    });
    Ok(handle)
}

pub fn speaker() -> SaySpeech {
    SaySpeech::new()
}

/// Speak a line via `say` without blocking the caller. Drops the result
/// — partner output that can't be spoken still prints to the bar.
pub fn speak_async(speaker: Arc<dyn AudioOutput>, line: String) {
    task::spawn_blocking(move || {
        if let Err(e) = speaker.speak(&line) {
            tracing::warn!(error = ?e, "say failed");
        }
    });
}

pub fn doctor() -> Result<()> {
    let mut ok = true;
    println!("nebulaos doctor — macOS");
    println!();

    print!("  /usr/bin/say                ");
    match std::process::Command::new("/usr/bin/say").arg("-v?").output() {
        Ok(out) if out.status.success() => println!("✓"),
        _ => {
            println!("✗ (missing? this should ship with every Mac)");
            ok = false;
        }
    }

    print!("  whisper model               ");
    let model = WhisperTranscriber::default_model_path();
    if model.exists() {
        println!("✓ {}", model.display());
    } else {
        println!("✗ missing");
        println!("    mkdir -p {}", model.parent().unwrap().display());
        println!("    curl -L -o {} \\", model.display());
        println!("      https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-tiny.bin");
        ok = false;
    }

    print!("  frontmost-app readable      ");
    match nebulaos_core::focus::frontmost_app_name() {
        Ok(Some(name)) => println!("✓ ({name})"),
        Ok(None) => println!("⚠ NSWorkspace returned no frontmost app"),
        Err(e) => {
            println!("✗ {e}");
            ok = false;
        }
    }

    print!("  ollama daemon (localhost)   ");
    let url = format!("{}/api/tags", "http://localhost:11434");
    let rt = tokio::runtime::Builder::new_current_thread()
        .enable_all()
        .build()?;
    let result: Result<reqwest::Response, _> = rt.block_on(async {
        reqwest::Client::builder()
            .timeout(Duration::from_secs(2))
            .build()?
            .get(&url)
            .send()
            .await
    });
    match result {
        Ok(r) if r.status().is_success() => println!("✓"),
        Ok(r) => println!("⚠ daemon up but returned {}", r.status()),
        Err(_) => println!("✗ unreachable (start `ollama serve` and `ollama pull hermes3:8b`)"),
    }

    print!("  anthropic api key           ");
    match std::env::var("ANTHROPIC_API_KEY") {
        Ok(_) => println!("✓"),
        Err(_) => println!("⚠ ANTHROPIC_API_KEY not set (Claude fallback unavailable)"),
    }

    print!("  data dir                    ");
    match paths::data_dir() {
        Ok(p) => {
            std::fs::create_dir_all(&p).ok();
            println!("✓ {}", p.display());
        }
        Err(e) => {
            println!("✗ {e}");
            ok = false;
        }
    }

    println!();
    if ok {
        println!("ready.");
    } else {
        println!("some checks failed — see above.");
        std::process::exit(1);
    }
    Ok(())
}

// Suppresses an unused-import warning when the binary isn't built with the
// mic path active.
#[allow(dead_code)]
fn _unused(_p: PathBuf) {}
