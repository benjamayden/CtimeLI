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


def _env_block_end_default(key: str, default: str) -> str:
    raw = os.environ.get(key, default).strip().lower()
    if raw not in _BLOCK_END_ACTIONS:
        return default
    return raw


@dataclass
class AppConfig:
    stroke_width: float = 6.0

    # Shake window: starts SHAKE_BEFORE_MINS before end (or last SHAKE_START_FRACTION if shorter).
    shake_before_mins: float = 7.0
    shake_start_fraction: float = 0.2
    shake_nudge_seconds: float = 10.0
    shake_nudge_level: float = 0.12
    shake_stop_before_mins: float = 2.0

    shake_max_x: float = 50.0
    shake_max_y: float = 50.0
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
            shake_before_mins=_env_float("SHAKE_BEFORE_MINS", 7.0),
            shake_start_fraction=_env_float("SHAKE_START_FRACTION", 0.2),
            shake_nudge_seconds=_env_float("SHAKE_NUDGE_SECONDS", 10.0),
            shake_nudge_level=_env_float("SHAKE_NUDGE_LEVEL", 0.12),
            shake_stop_before_mins=_env_float("SHAKE_STOP_BEFORE_MINS", 2.0),
            shake_max_x=_env_float("SHAKE_MAX_X", 50.0),
            shake_max_y=_env_float("SHAKE_MAX_Y", 50.0),
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


def shake_intensity(remaining_sec: float, total_sec: float, cfg: AppConfig) -> float:
    """0..1 shake strength from time remaining."""
    if remaining_sec <= 0 or total_sec <= 0:
        return 0.0

    before_sec = cfg.shake_before_mins * 60.0
    if total_sec < before_sec:
        start_remaining = total_sec * cfg.shake_start_fraction
        # Short timer: calm period scales down (min 2s), not full 2 minutes.
        stop_remaining = min(
            cfg.shake_stop_before_mins * 60.0,
            max(0.5, start_remaining * 0.08),
        )
    else:
        start_remaining = before_sec
        stop_remaining = cfg.shake_stop_before_mins * 60.0

    stop_remaining = min(stop_remaining, start_remaining * 0.85)

    if remaining_sec > start_remaining or remaining_sec <= stop_remaining:
        return 0.0

    zone = start_remaining - stop_remaining
    elapsed = start_remaining - remaining_sec
    nudge = min(cfg.shake_nudge_seconds, zone * 0.45)

    if elapsed < nudge:
        return cfg.shake_nudge_level * _smoothstep(elapsed / max(nudge, 0.001))

    ramp_t = (elapsed - nudge) / max(0.001, zone - nudge)
    return cfg.shake_nudge_level + (1.0 - cfg.shake_nudge_level) * _smoothstep(ramp_t)


def _smoothstep(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return t * t * (3.0 - 2.0 * t)
