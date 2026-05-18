//! Claude API client. Text-only summaries, never raw audio or screenshots.
//! Reads ANTHROPIC_API_KEY from the env. Default model is the latest Sonnet
//! — fast enough for in-session use, cheap enough to call sparingly.

use std::time::Duration;

use anyhow::{Context, Result, anyhow};
use async_trait::async_trait;
use serde::{Deserialize, Serialize};

use super::Fallback;
use crate::partner::SYSTEM_PROMPT;

const DEFAULT_MODEL: &str = "claude-sonnet-4-6";
const ANTHROPIC_URL: &str = "https://api.anthropic.com/v1/messages";
const ANTHROPIC_VERSION: &str = "2023-06-01";
const MAX_TOKENS: u32 = 512;

pub struct ClaudeFallback {
    api_key: String,
    model: String,
    client: reqwest::Client,
}

impl ClaudeFallback {
    pub fn new(api_key: impl Into<String>) -> Result<Self> {
        Self::with_model(api_key, DEFAULT_MODEL)
    }

    pub fn with_model(api_key: impl Into<String>, model: impl Into<String>) -> Result<Self> {
        let client = reqwest::Client::builder()
            .timeout(Duration::from_secs(60))
            .build()
            .context("building reqwest client")?;
        Ok(Self {
            api_key: api_key.into(),
            model: model.into(),
            client,
        })
    }

    /// Convenience constructor that reads ANTHROPIC_API_KEY from the env.
    pub fn from_env() -> Result<Self> {
        let key = std::env::var("ANTHROPIC_API_KEY")
            .context("ANTHROPIC_API_KEY not set")?;
        Self::new(key)
    }

    fn build_request<'a>(&'a self, summary: &str) -> MessagesRequest<'a> {
        MessagesRequest {
            model: &self.model,
            max_tokens: MAX_TOKENS,
            system: SYSTEM_PROMPT,
            messages: vec![Message {
                role: "user",
                content: summary.to_string(),
            }],
        }
    }
}

#[async_trait]
impl Fallback for ClaudeFallback {
    async fn reason(&self, summary: &str) -> Result<String> {
        let body = self.build_request(summary);
        let resp = self
            .client
            .post(ANTHROPIC_URL)
            .header("x-api-key", &self.api_key)
            .header("anthropic-version", ANTHROPIC_VERSION)
            .header("content-type", "application/json")
            .json(&body)
            .send()
            .await
            .context("POST anthropic /v1/messages")?;
        if !resp.status().is_success() {
            let status = resp.status();
            let body = resp.text().await.unwrap_or_default();
            return Err(anyhow!("anthropic returned {status}: {body}"));
        }
        let parsed: MessagesResponse = resp.json().await.context("decoding anthropic response")?;
        let text = parsed
            .content
            .into_iter()
            .map(|ContentBlock::Text { text }| text)
            .collect::<Vec<_>>()
            .join("\n");
        Ok(text.trim().to_string())
    }
}

#[derive(Serialize)]
struct MessagesRequest<'a> {
    model: &'a str,
    max_tokens: u32,
    system: &'a str,
    messages: Vec<Message>,
}

#[derive(Serialize)]
struct Message {
    role: &'static str,
    content: String,
}

#[derive(Deserialize)]
struct MessagesResponse {
    content: Vec<ContentBlock>,
}

#[derive(Deserialize)]
#[serde(tag = "type", rename_all = "lowercase")]
enum ContentBlock {
    Text { text: String },
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn request_carries_system_prompt_and_user_message() {
        let f = ClaudeFallback::new("sk-test").unwrap();
        let req = f.build_request("session went off-task at 23 min — what should I say?");
        assert!(req.system.contains("Nebulaos"));
        assert_eq!(req.messages.len(), 1);
        assert_eq!(req.messages[0].role, "user");
        assert!(req.messages[0].content.contains("23 min"));
        assert_eq!(req.max_tokens, MAX_TOKENS);
    }
}
