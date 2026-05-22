"""AppConfig — the immutable configuration value object.

This is pure data plus pure transforms (parse a mapping, merge overrides). It
does NOT read files or os.environ — that I/O lives in the dotenv adapter and
the composition root. See docs/configuration.md.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, fields, replace

from .apps import AppSelector
from .manifest import resolve_block_end_csv

_BLOCK_END_ACTIONS = frozenset({"minimize", "hide", "quit", "skip"})

# PULSE_RAMP preset name -> spread-curve exponent.
_PULSE_RAMP_PRESETS: dict[str, float] = {"linear": 1.0, "late": 3.0}


@dataclass(frozen=True)
class AppConfig:
    """Every tunable. Defaults shown are the built-in defaults."""

    # Stroke
    stroke_width: float = 6.0
    red_zone_fraction: float = 0.05

    # Edge glow (pulse)
    pulse_before_secs: float = 120.0
    pulse_opacity_ramp_secs: float = 10.0
    pulse_max_opacity: float = 0.85
    pulse_depth_min: float = 10.0
    pulse_depth_max: float = 110.0
    pulse_ramp_power: float = 1.0
    pulse_visual_power: float = 1.0

    # Window wiggle
    shake_wiggle_seconds: float = 3.0
    shake_max_x: float = 28.0
    shake_max_y: float = 28.0
    shake_speed: float = 10.0
    shake_speed_x: float = 10.0
    shake_speed_y: float = 10.0
    shake_smooth: float = 14.0

    # Block-on-end
    block_on_end: bool = False
    block_end_default: str = "minimize"
    block_end_minimize: frozenset[AppSelector] = frozenset()
    block_end_hide: frozenset[AppSelector] = frozenset()
    block_end_quit: frozenset[AppSelector] = frozenset()
    block_end_skip: frozenset[AppSelector] = frozenset()

    # Calendar (watch mode)
    calendar_enabled: bool = True
    calendar_poll_seconds: float = 15.0
    calendar_window_minutes: float = 10.0
    calendar_block_before_mins: float = 7.0
    calendar_stroke_r: float = 0.30
    calendar_stroke_g: float = 0.85
    calendar_stroke_b: float = 0.45

    @classmethod
    def from_mapping(
        cls,
        env: Mapping[str, str],
        manifest: dict[int, str] | None = None,
    ) -> tuple[AppConfig, list[str]]:
        """Build from a string mapping (merged process env over .env values).

        Returns (config, warnings) where warnings are stale manifest index tokens
        (e.g. ["5", "7"] when those indices don't appear in the manifest).
        Pass manifest=None or omit it to skip index resolution.
        """
        manifest = manifest or {}
        minimize_sel, w1 = resolve_block_end_csv(env.get("BLOCK_END_MINIMIZE", ""), manifest)
        hide_sel, w2 = resolve_block_end_csv(env.get("BLOCK_END_HIDE", ""), manifest)
        quit_sel, w3 = resolve_block_end_csv(env.get("BLOCK_END_QUIT", ""), manifest)
        skip_sel, w4 = resolve_block_end_csv(env.get("BLOCK_END_SKIP", ""), manifest)
        warnings = [
            f"BLOCK_END_MINIMIZE index {t} not in apps.manifest — run ./run apps" for t in w1
        ] + [
            f"BLOCK_END_HIDE index {t} not in apps.manifest — run ./run apps" for t in w2
        ] + [
            f"BLOCK_END_QUIT index {t} not in apps.manifest — run ./run apps" for t in w3
        ] + [
            f"BLOCK_END_SKIP index {t} not in apps.manifest — run ./run apps" for t in w4
        ]
        cfg = cls(
            stroke_width=_as_float(env, "STROKE_WIDTH", 6.0),
            red_zone_fraction=_as_float(env, "RED_ZONE_FRACTION", 0.05),
            pulse_before_secs=_as_float(env, "PULSE_BEFORE_SECS", 120.0),
            pulse_opacity_ramp_secs=_as_float(env, "PULSE_OPACITY_RAMP_SECS", 10.0),
            pulse_max_opacity=_as_float(env, "PULSE_MAX_OPACITY", 0.85),
            pulse_depth_min=_as_float(env, "PULSE_DEPTH_MIN", 10.0),
            pulse_depth_max=_as_float(env, "PULSE_DEPTH_MAX", 110.0),
            pulse_ramp_power=_pulse_ramp_power(env),
            pulse_visual_power=_as_float(env, "PULSE_VISUAL_POWER", 1.0),
            shake_wiggle_seconds=_as_float(env, "SHAKE_WIGGLE_SECONDS", 3.0),
            shake_max_x=_as_float(env, "SHAKE_MAX_X", 28.0),
            shake_max_y=_as_float(env, "SHAKE_MAX_Y", 28.0),
            shake_speed=_as_float(env, "SHAKE_SPEED", 10.0),
            shake_speed_x=_as_float(env, "SHAKE_SPEED_X", 10.0),
            shake_speed_y=_as_float(env, "SHAKE_SPEED_Y", 10.0),
            shake_smooth=_as_float(env, "SHAKE_SMOOTH", 14.0),
            block_on_end=_as_bool(env, "BLOCK_ON_END", False),
            block_end_default=_as_action(env, "BLOCK_END_DEFAULT", "minimize"),
            block_end_minimize=minimize_sel,
            block_end_hide=hide_sel,
            block_end_quit=quit_sel,
            block_end_skip=skip_sel,
            calendar_enabled=_as_bool(env, "CALENDAR_ENABLED", True),
            calendar_poll_seconds=_as_float(env, "CALENDAR_POLL_SECONDS", 15.0),
            calendar_window_minutes=_as_float(env, "CALENDAR_WINDOW_MINUTES", 10.0),
            calendar_block_before_mins=_as_float(env, "CALENDAR_BLOCK_BEFORE_MINS", 7.0),
            calendar_stroke_r=_as_float(env, "CALENDAR_STROKE_R", 0.30),
            calendar_stroke_g=_as_float(env, "CALENDAR_STROKE_G", 0.85),
            calendar_stroke_b=_as_float(env, "CALENDAR_STROKE_B", 0.45),
        )
        return cfg, warnings

    def merge(self, **overrides: object) -> AppConfig:
        """Return a copy with non-None overrides applied.

        Unknown keys raise (guards typo'd CLI wiring) — see edge-cases.md #6.
        """
        known = {f.name for f in fields(self)}
        applied: dict[str, object] = {}
        for key, value in overrides.items():
            if key not in known:
                raise ValueError(f"unknown AppConfig override: {key!r}")
            if value is not None:
                applied[key] = value
        return replace(self, **applied)


def _as_float(env: Mapping[str, str], key: str, default: float) -> float:
    raw = env.get(key)
    return default if raw is None else float(raw)


def _as_bool(env: Mapping[str, str], key: str, default: bool) -> bool:
    raw = env.get(key)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _as_action(env: Mapping[str, str], key: str, default: str) -> str:
    raw = (env.get(key) or default).strip().lower()
    return raw if raw in _BLOCK_END_ACTIONS else default


def _pulse_ramp_power(env: Mapping[str, str]) -> float:
    """PULSE_RAMP_POWER (raw exponent) overrides the PULSE_RAMP preset name."""
    if env.get("PULSE_RAMP_POWER") is not None:
        return _as_float(env, "PULSE_RAMP_POWER", 1.0)
    preset = (env.get("PULSE_RAMP") or "linear").strip().lower()
    return _PULSE_RAMP_PRESETS.get(preset, 1.0)
