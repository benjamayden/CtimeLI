"""Animation curves: edge glow and screen blur. See docs/domain.md section 2.

Each curve takes `remaining` (seconds left) and an AppConfig, and returns a
number the overlay or blur port renders directly. The curves are independent.
"""

from __future__ import annotations

from .config import AppConfig
from .math import clamp, smoothstep


def _pulse_window_elapsed(remaining: float, cfg: AppConfig) -> float | None:
    """Seconds since the pulse window opened, or None if outside the window."""
    window = max(1.0, cfg.pulse_before_secs)
    if remaining <= 0.0 or remaining > window:
        return None
    return window - remaining


def pulse_opacity(remaining: float, cfg: AppConfig) -> float:
    """Edge-glow brightness, 0 .. cfg.pulse_max_opacity.

    Ramps in over the first `pulse_opacity_ramp_secs` of the pulse window,
    then holds. The max(0.5, ...) guards a zero-length ramp.
    """
    elapsed = _pulse_window_elapsed(remaining, cfg)
    if elapsed is None:
        return 0.0
    ramp = max(0.5, cfg.pulse_opacity_ramp_secs)
    u = min(1.0, elapsed / ramp)
    return cfg.pulse_max_opacity * smoothstep(u)


def pulse_spread(remaining: float, cfg: AppConfig) -> float:
    """How far the glow reaches inward, 0 .. 1.

    Grows across the whole pulse window, shaped by pulse_ramp_power
    (1 = linear, 3 = late/cubic).
    """
    elapsed = _pulse_window_elapsed(remaining, cfg)
    if elapsed is None:
        return 0.0
    window = max(1.0, cfg.pulse_before_secs)
    t = clamp(elapsed / window, 0.0, 1.0)
    return t**cfg.pulse_ramp_power


def blur_intensity(remaining: float, cfg: AppConfig) -> float:
    """Full-screen blur strength, 0 .. 1, over the pulse (glow) window.

    Shares the glow window and spread ramp shape — blur starts when the edge
    glow opens and reaches 1.0 at zero.
    """
    if remaining <= 0.0:
        return 1.0
    return pulse_spread(remaining, cfg)
