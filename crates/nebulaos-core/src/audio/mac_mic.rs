//! Microphone capture on macOS via `cpal` (CoreAudio backend).
//!
//! Push-to-talk style: `MacMicCapture::start()` opens the default input
//! stream and returns a `CaptureHandle`. `handle.stop()` drains the buffer
//! and returns 16 kHz mono i16 PCM, the format Whisper expects.
//!
//! Resampling is naive — linear interpolation. Whisper Tiny is forgiving;
//! good enough for a 5-10s goal declaration. Replace with `rubato` if you
//! need higher quality later.

use std::sync::{Arc, Mutex};

use anyhow::{Context, Result, anyhow};
use cpal::SampleFormat;
use cpal::traits::{DeviceTrait, HostTrait, StreamTrait};

const TARGET_SAMPLE_RATE: u32 = 16_000;

pub struct MacMicCapture;

impl MacMicCapture {
    /// Begin capturing from the default input device. The returned handle
    /// keeps the stream alive; drop it or call `stop()` to end capture.
    pub fn start() -> Result<CaptureHandle> {
        let host = cpal::default_host();
        let device = host
            .default_input_device()
            .ok_or_else(|| anyhow!("no default input device — grant mic access in System Settings"))?;
        let config = device
            .default_input_config()
            .context("read default input config")?;

        let source_rate = config.sample_rate().0;
        let channels = config.channels() as usize;
        let buffer: Arc<Mutex<Vec<f32>>> = Arc::new(Mutex::new(Vec::with_capacity(source_rate as usize * 10)));

        let buf_writer = buffer.clone();
        let err_fn = |err| tracing::warn!(error = ?err, "cpal stream error");

        let stream = match config.sample_format() {
            SampleFormat::F32 => {
                let cfg = config.into();
                device.build_input_stream(
                    &cfg,
                    move |data: &[f32], _| append_mono(&buf_writer, data, channels),
                    err_fn,
                    None,
                )
            }
            SampleFormat::I16 => {
                let cfg = config.into();
                device.build_input_stream(
                    &cfg,
                    move |data: &[i16], _| {
                        let mut owned = Vec::with_capacity(data.len());
                        for s in data {
                            owned.push(*s as f32 / i16::MAX as f32);
                        }
                        append_mono(&buf_writer, &owned, channels);
                    },
                    err_fn,
                    None,
                )
            }
            SampleFormat::U16 => {
                let cfg = config.into();
                device.build_input_stream(
                    &cfg,
                    move |data: &[u16], _| {
                        let mut owned = Vec::with_capacity(data.len());
                        for s in data {
                            owned.push((*s as f32 - u16::MAX as f32 / 2.0) / (u16::MAX as f32 / 2.0));
                        }
                        append_mono(&buf_writer, &owned, channels);
                    },
                    err_fn,
                    None,
                )
            }
            other => return Err(anyhow!("unsupported input sample format: {other:?}")),
        }
        .context("build cpal input stream")?;

        stream.play().context("start cpal input stream")?;
        Ok(CaptureHandle { stream, buffer, source_rate })
    }
}

/// Active capture session. Keep alive while recording; call `stop()` to end.
pub struct CaptureHandle {
    stream: cpal::Stream,
    buffer: Arc<Mutex<Vec<f32>>>,
    source_rate: u32,
}

impl CaptureHandle {
    pub fn stop(self) -> Result<Vec<i16>> {
        drop(self.stream);
        let samples = self.buffer.lock().expect("capture buffer poisoned").clone();
        Ok(resample_to_i16_16k(&samples, self.source_rate))
    }
}

fn append_mono(buf: &Arc<Mutex<Vec<f32>>>, frame: &[f32], channels: usize) {
    let mut lock = buf.lock().expect("capture buffer poisoned");
    if channels <= 1 {
        lock.extend_from_slice(frame);
        return;
    }
    for chunk in frame.chunks_exact(channels) {
        let sum: f32 = chunk.iter().sum();
        lock.push(sum / channels as f32);
    }
}

fn resample_to_i16_16k(samples: &[f32], source_rate: u32) -> Vec<i16> {
    if samples.is_empty() {
        return Vec::new();
    }
    let to_i16 = |x: f32| -> i16 {
        let clamped = x.clamp(-1.0, 1.0);
        (clamped * i16::MAX as f32) as i16
    };
    if source_rate == TARGET_SAMPLE_RATE {
        return samples.iter().map(|s| to_i16(*s)).collect();
    }
    let ratio = source_rate as f64 / TARGET_SAMPLE_RATE as f64;
    let out_len = (samples.len() as f64 / ratio) as usize;
    let mut out = Vec::with_capacity(out_len);
    for i in 0..out_len {
        let src_pos = i as f64 * ratio;
        let idx = src_pos as usize;
        let next = (idx + 1).min(samples.len() - 1);
        let frac = (src_pos - idx as f64) as f32;
        let a = samples[idx];
        let b = samples[next];
        out.push(to_i16(a + (b - a) * frac));
    }
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn downsample_halves_at_2x_rate() {
        // Source: 32 kHz, target: 16 kHz → ratio 2.0 → out_len ≈ input_len / 2.
        let input: Vec<f32> = (0..1000).map(|i| (i as f32) / 1000.0).collect();
        let out = resample_to_i16_16k(&input, 32_000);
        assert!((out.len() as i64 - 500).abs() <= 1);
    }

    #[test]
    fn passthrough_when_already_16k() {
        let input = vec![0.5_f32; 10];
        let out = resample_to_i16_16k(&input, 16_000);
        assert_eq!(out.len(), 10);
        assert!(out.iter().all(|s| *s > 0));
    }
}
