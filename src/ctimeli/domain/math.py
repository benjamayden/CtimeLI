"""Math primitives. See docs/domain.md section 1."""

from __future__ import annotations

import math


def clamp(value: float, lo: float, hi: float) -> float:
    """Constrain value to [lo, hi]."""
    return max(lo, min(hi, value))


def smoothstep(t: float) -> float:
    """S-curve ramp on [0, 1] with zero slope at both ends.

    smoothstep(0) == 0, smoothstep(1) == 1, smoothstep(0.5) == 0.5.
    """
    t = clamp(t, 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def lerp(current: float, target: float, dt: float, rate: float) -> float:
    """Frame-rate-independent exponential approach toward target.

    The exp(-rate*dt) form converges the same amount per wall-clock second
    regardless of frame rate, so animation looks identical at 30 or 120 Hz.
    """
    alpha = 1.0 - math.exp(-rate * dt)
    return current + (target - current) * alpha


def format_duration(seconds: float) -> str:
    """Human-readable duration: '1h 2m 5s' / '1m 4s' / '9s'.

    Negative input clamps to '0s'; fractional input truncates.
    """
    total = max(0, int(seconds))
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours}h {minutes}m {secs}s"
    if minutes:
        return f"{minutes}m {secs}s"
    return f"{secs}s"
