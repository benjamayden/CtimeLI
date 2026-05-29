"""Animation curves: edge glow and screen blur. See docs/domain.md section 2.

Each curve takes `fraction_remaining` (0..1) and an AppConfig, and returns a
number the overlay or blur port renders directly. The curves are independent.
"""

from __future__ import annotations

from .config import AppConfig
from .math import clamp, smoothstep


def _pulse_window_elapsed(fraction_remaining: float, cfg: AppConfig) -> float | None:
    """Fraction since the pulse window opened, or None if outside the window."""
    window = max(0.0, min(1.0, cfg.pulse_before_fraction))
    if window <= 0.0 or fraction_remaining <= 0.0 or fraction_remaining > window:
        return None
    return window - fraction_remaining


def pulse_opacity(fraction_remaining: float, cfg: AppConfig) -> float:
    """Edge-glow brightness, 0 .. cfg.pulse_max_opacity.

    Ramps in over the first `pulse_opacity_ramp_fraction` of the pulse window,
    then holds. The max(0.001, ...) guards a zero-length ramp.
    """
    elapsed = _pulse_window_elapsed(fraction_remaining, cfg)
    if elapsed is None:
        return 0.0
    ramp = max(0.001, min(cfg.pulse_before_fraction, cfg.pulse_opacity_ramp_fraction))
    u = min(1.0, elapsed / ramp)
    return cfg.pulse_max_opacity * smoothstep(u)


def pulse_spread(fraction_remaining: float, cfg: AppConfig) -> float:
    """How far the glow reaches inward, 0 .. 1.

    Grows across the whole pulse window, shaped by pulse_ramp_power
    (1 = linear, 3 = late/cubic).
    """
    elapsed = _pulse_window_elapsed(fraction_remaining, cfg)
    if elapsed is None:
        return 0.0
    window = max(0.001, min(1.0, cfg.pulse_before_fraction))
    t = clamp(elapsed / window, 0.0, 1.0)
    return t**cfg.pulse_ramp_power


def _blur_window_elapsed(fraction_remaining: float, cfg: AppConfig) -> float | None:
    """Fraction since the blur window opened, or None if outside the window."""
    window = max(0.0, min(1.0, cfg.blur_before_fraction))
    if window <= 0.0 or fraction_remaining <= 0.0 or fraction_remaining > window:
        return None
    return window - fraction_remaining


def blur_intensity(fraction_remaining: float, cfg: AppConfig) -> float:
    """Full-screen blur strength, 0 .. 1, over ``blur_before_fraction``.

    Uses the same spread ramp shape as the edge glow (``pulse_ramp_power``).
    """
    if fraction_remaining <= 0.0:
        return 1.0
    elapsed = _blur_window_elapsed(fraction_remaining, cfg)
    if elapsed is None:
        return 0.0
    window = max(0.001, min(1.0, cfg.blur_before_fraction))
    t = clamp(elapsed / window, 0.0, 1.0)
    return t**cfg.pulse_ramp_power
