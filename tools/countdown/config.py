"""Countdown configuration from .env and CLI overrides."""

from __future__ import annotations

import os
from dataclasses import dataclass, fields
from pathlib import Path

_ENV_DIR = Path(__file__).resolve().parent


def load_dotenv(path: Path | None = None) -> None:
    path = path or (_ENV_DIR / ".env")
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = val


def _env_str(key: str, default: str) -> str:
    return os.environ.get(key, default)


def _env_float(key: str, default: float) -> float:
    raw = os.environ.get(key)
    if raw is None:
        return default
    return float(raw)


def _env_bool(key: str, default: bool) -> bool:
    raw = os.environ.get(key)
    if raw is None:
        return default
    return raw.lower() in {"1", "true", "yes", "on"}


def _env_csv(key: str) -> frozenset[str]:
    raw = os.environ.get(key, "").strip()
    if not raw:
        return frozenset()
    return frozenset(part.strip() for part in raw.split(",") if part.strip())


_BLOCK_END_ACTIONS = frozenset({"minimize", "hide", "quit", "skip"})

# PULSE_RAMP preset → exponent on normalized window progress (t = 0 at window open, 1 at zero).
_PULSE_RAMP_PRESETS: dict[str, float] = {
    "linear": 1.0,
    "late": 3.0,
}


def _env_pulse_ramp_power() -> float:
    """PULSE_RAMP_POWER overrides PULSE_RAMP preset."""
    if os.environ.get("PULSE_RAMP_POWER") is not None:
        return _env_float("PULSE_RAMP_POWER", 1.0)
    preset = _env_str("PULSE_RAMP", "linear").strip().lower()
    return _PULSE_RAMP_PRESETS.get(preset, 1.0)


def _env_block_end_default(key: str, default: str) -> str:
    raw = os.environ.get(key, default).strip().lower()
    if raw not in _BLOCK_END_ACTIONS:
        return default
    return raw


@dataclass
class AppConfig:
    stroke_width: float = 6.0

    # Edge pulse: glow window + opacity vs spread (depth) curves.
    pulse_before_secs: float = 120.0
    pulse_opacity_ramp_secs: float = 10.0  # reach pulse_max_opacity within this many seconds
    pulse_max_opacity: float = 0.85  # peak edge-glow alpha (0–1)
    pulse_depth_min: float = 10.0  # glow depth in px at pulse window start
    pulse_depth_max: float = 110.0  # max depth at zero (~25% over old 88px)
    pulse_ramp_power: float = 1.0  # spread curve: 1=linear, 3=late/cubic (PULSE_RAMP)
    pulse_visual_power: float = 1.0  # extra spread shaping in draw (legacy)
    # Window wiggle: only the final SHAKE_WIGGLE_SECONDS (default 3s).
    shake_wiggle_seconds: float = 3.0

    # Legacy .env keys — loaded but no longer control timing (use pulse/wiggle above).
    shake_before_mins: float = 7.0
    shake_start_fraction: float = 0.2
    shake_nudge_seconds: float = 10.0
    shake_nudge_level: float = 0.12
    shake_stop_before_mins: float = 2.0

    shake_max_x: float = 28.0
    shake_max_y: float = 28.0
    shake_speed: float = 10.0
    shake_speed_x: float = 10.0
    shake_speed_y: float = 10.0
    shake_smooth: float = 14.0

    red_zone_fraction: float = 0.05
    block_on_end: bool = False
    # Per-app behavior when block-on-end overlay is dismissed (process names, comma-separated).
    block_end_default: str = "minimize"
    block_end_minimize: frozenset[str] = frozenset()
    block_end_hide: frozenset[str] = frozenset()
    block_end_quit: frozenset[str] = frozenset()
    block_end_skip: frozenset[str] = frozenset()
    calendar_enabled: bool = True
    calendar_poll_seconds: float = 15.0
    calendar_window_minutes: float = 10.0
    calendar_block_before_mins: float = 7.0
    calendar_stroke_r: float = 0.3
    calendar_stroke_g: float = 0.85
    calendar_stroke_b: float = 0.45

    @classmethod
    def from_env(cls) -> AppConfig:
        load_dotenv()
        return cls(
            stroke_width=_env_float("STROKE_WIDTH", 6.0),
            pulse_before_secs=_env_float("PULSE_BEFORE_SECS", 120.0),
            pulse_opacity_ramp_secs=_env_float("PULSE_OPACITY_RAMP_SECS", 10.0),
            pulse_max_opacity=_env_float("PULSE_MAX_OPACITY", 0.85),
            pulse_depth_min=_env_float("PULSE_DEPTH_MIN", 10.0),
            pulse_depth_max=_env_float("PULSE_DEPTH_MAX", 110.0),
            pulse_ramp_power=_env_pulse_ramp_power(),
            pulse_visual_power=_env_float("PULSE_VISUAL_POWER", 1.0),
            shake_wiggle_seconds=_env_float("SHAKE_WIGGLE_SECONDS", 3.0),
            shake_before_mins=_env_float("SHAKE_BEFORE_MINS", 7.0),
            shake_start_fraction=_env_float("SHAKE_START_FRACTION", 0.2),
            shake_nudge_seconds=_env_float("SHAKE_NUDGE_SECONDS", 10.0),
            shake_nudge_level=_env_float("SHAKE_NUDGE_LEVEL", 0.12),
            shake_stop_before_mins=_env_float("SHAKE_STOP_BEFORE_MINS", 2.0),
            shake_max_x=_env_float("SHAKE_MAX_X", 28.0),
            shake_max_y=_env_float("SHAKE_MAX_Y", 28.0),
            shake_speed=_env_float("SHAKE_SPEED", 10.0),
            shake_speed_x=_env_float("SHAKE_SPEED_X", 10.0),
            shake_speed_y=_env_float("SHAKE_SPEED_Y", 10.0),
            shake_smooth=_env_float("SHAKE_SMOOTH", 14.0),
            red_zone_fraction=_env_float("RED_ZONE_FRACTION", 0.05),
            block_on_end=_env_bool("BLOCK_ON_END", False),
            block_end_default=_env_block_end_default("BLOCK_END_DEFAULT", "minimize"),
            block_end_minimize=_env_csv("BLOCK_END_MINIMIZE"),
            block_end_hide=_env_csv("BLOCK_END_HIDE"),
            block_end_quit=_env_csv("BLOCK_END_QUIT"),
            block_end_skip=_env_csv("BLOCK_END_SKIP"),
            calendar_enabled=_env_bool("CALENDAR_ENABLED", True),
            calendar_poll_seconds=_env_float("CALENDAR_POLL_SECONDS", 15.0),
            calendar_window_minutes=_env_float("CALENDAR_WINDOW_MINUTES", 10.0),
            calendar_block_before_mins=_env_float("CALENDAR_BLOCK_BEFORE_MINS", 7.0),
            calendar_stroke_r=_env_float("CALENDAR_STROKE_R", 0.3),
            calendar_stroke_g=_env_float("CALENDAR_STROKE_G", 0.85),
            calendar_stroke_b=_env_float("CALENDAR_STROKE_B", 0.45),
        )

    def merge_cli(self, **overrides) -> AppConfig:
        data = {f.name: getattr(self, f.name) for f in fields(self)}
        for key, val in overrides.items():
            if val is not None:
                data[key] = val
        return AppConfig(**data)


def _pulse_window_elapsed(remaining_sec: float, cfg: AppConfig) -> float | None:
    window = max(1.0, cfg.pulse_before_secs)
    if remaining_sec <= 0 or remaining_sec > window:
        return None
    return window - remaining_sec


def pulse_opacity(remaining_sec: float, cfg: AppConfig) -> float:
    """0..pulse_max_opacity — ramps quickly at the start of the pulse window."""
    elapsed = _pulse_window_elapsed(remaining_sec, cfg)
    if elapsed is None:
        return 0.0
    ramp = max(0.5, cfg.pulse_opacity_ramp_secs)
    u = min(1.0, elapsed / ramp)
    return cfg.pulse_max_opacity * _smoothstep(u)


def pulse_spread(remaining_sec: float, cfg: AppConfig) -> float:
    """0..1 — how far the glow encroaches inward; grows over the full pulse window."""
    elapsed = _pulse_window_elapsed(remaining_sec, cfg)
    if elapsed is None:
        return 0.0
    window = max(1.0, cfg.pulse_before_secs)
    t = max(0.0, min(1.0, elapsed / window))
    return t ** cfg.pulse_ramp_power


def pulse_intensity(remaining_sec: float, cfg: AppConfig) -> float:
    """Deprecated alias — spread only."""
    return pulse_spread(remaining_sec, cfg)


def shake_intensity(remaining_sec: float, total_sec: float, cfg: AppConfig) -> float:
    """0..1 window wiggle strength — only the final shake_wiggle_seconds."""
    _ = total_sec
    wiggle = max(0.5, cfg.shake_wiggle_seconds)
    if remaining_sec <= 0 or remaining_sec > wiggle:
        return 0.0
    return _smoothstep(1.0 - remaining_sec / wiggle)


def _smoothstep(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return t * t * (3.0 - 2.0 * t)
