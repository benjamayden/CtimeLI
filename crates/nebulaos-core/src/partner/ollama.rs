//! Ollama HTTP client for the thinking partner. Talks to a local daemon over
//! `/api/chat`. Streaming is off — the partner replies in short sentences.

use std::time::Duration;

use anyhow::{Context, Result, anyhow};
use serde::{Deserialize, Serialize};

use super::{Partner, SYSTEM_PROMPT};

const SILENCE_SIGNAL: &str = ".";

#[derive(Debug, Clone)]
pub struct OllamaPartner {
    base_url: String,
    model: String,
    client: reqwest::Client,
}

impl OllamaPartner {
    pub fn new(base_url: impl Into<String>, model: impl Into<String>) -> Result<Self> {
        let client = reqwest::Client::builder()
            .timeout(Duration::from_secs(30))
            .build()
            .context("building reqwest client")?;
        Ok(Self {
            base_url: base_url.into(),
            model: model.into(),
            client,
        })
    }

    fn build_request(&self, user_utterance: &str, context: &str) -> ChatRequest<'_> {
        let user_content = if context.is_empty() {
            user_utterance.to_string()
        } else {
            format!("Context:\n{context}\n\nThey said:\n{user_utterance}")
        };
        ChatRequest {
            model: &self.model,
            stream: false,
            messages: vec![
                Message { role: "system", content: SYSTEM_PROMPT.into() },
                Message { role: "user", content: user_content },
            ],
        }
    }
}

#[async_trait::async_trait]
impl Partner for OllamaPartner {
    async fn respond(&self, user_utterance: &str, context: &str) -> Result<Option<String>> {
        let body = self.build_request(user_utterance, context);
        let url = format!("{}/api/chat", self.base_url.trim_end_matches('/'));
        let resp = self
            .client
            .post(&url)
            .json(&body)
            .send()
            .await
            .with_context(|| format!("POST {url}"))?;
        if !resp.status().is_success() {
            return Err(anyhow!("ollama returned {}", resp.status()));
        }
        let parsed: ChatResponse = resp.json().await.context("decoding ollama response")?;
        let text = parsed.message.content.trim().to_string();
        if text.is_empty() || text == SILENCE_SIGNAL {
            Ok(None)
        } else {
            Ok(Some(text))
        }
    }
}

#[derive(Serialize)]
struct ChatRequest<'a> {
    model: &'a str,
    stream: bool,
    messages: Vec<Message>,
}

#[derive(Serialize, Deserialize)]
struct Message {
    role: &'static str,
    content: String,
}

#[derive(Deserialize)]
struct ChatResponse {
    message: ResponseMessage,
}

#[derive(Deserialize)]
struct ResponseMessage {
    #[allow(dead_code)]
    role: String,
    content: String,
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn request_carries_system_then_user() {
        let p = OllamaPartner::new("http://localhost:11434", "hermes3:8b").unwrap();
        let req = p.build_request("I'm stuck on the hero", "goal: draft the copy");
        assert_eq!(req.model, "hermes3:8b");
        assert!(!req.stream);
        assert_eq!(req.messages.len(), 2);
        assert_eq!(req.messages[0].role, "system");
        assert!(req.messages[0].content.contains("Nebulaos"));
        assert_eq!(req.messages[1].role, "user");
        assert!(req.messages[1].content.contains("draft the copy"));
        assert!(req.messages[1].content.contains("I'm stuck on the hero"));
    }

    #[test]
    fn no_context_skips_context_block() {
        let p = OllamaPartner::new("http://localhost:11434", "hermes3:8b").unwrap();
        let req = p.build_request("hello", "");
        assert_eq!(req.messages[1].content, "hello");
    }
}
