"""Window-wiggle motion — the pure offset generator. See docs/domain.md.

ShakeMotion turns a 0..1 intensity into a smoothed (dx, dy) pixel offset. It is
stateful (phase + smoothing) but pure: deterministic given its inputs, no I/O.
The WindowShaker adapter just applies the offset it produces; the standalone
shake-tuning harness drives this same class (DRY — see edge-cases.md #10).
"""

from __future__ import annotations

import math

from .config import AppConfig
from .math import lerp


class ShakeMotion:
    """Generates a two-frequency, smoothed wiggle offset frame by frame."""

    def __init__(self, cfg: AppConfig) -> None:
        self.cfg = cfg
        self._phase = 0.0
        self._dx = 0.0
        self._dy = 0.0

    def reset(self) -> None:
        """Drop all motion state (call when the wiggle window closes)."""
        self._phase = 0.0
        self._dx = 0.0
        self._dy = 0.0

    def offset(self, intensity: float, dt_seconds: float) -> tuple[float, float]:
        """Next (dx, dy) offset for the given wiggle intensity (0..1)."""
        if intensity <= 0.0:
            self.reset()
            return (0.0, 0.0)

        cfg = self.cfg
        self._phase += dt_seconds * cfg.shake_speed * (0.4 + intensity * 0.6)
        wave = (
            math.sin(self._phase) * 0.65
            + math.sin(self._phase * 0.55 + 0.8) * 0.35
        )
        target_dx = (
            cfg.shake_max_x * wave * intensity * math.sin(self._phase * cfg.shake_speed_x)
        )
        target_dy = (
            cfg.shake_max_y
            * wave
            * intensity
            * math.cos(self._phase * cfg.shake_speed_y + 0.4)
        )
        self._dx = lerp(self._dx, target_dx, dt_seconds, cfg.shake_smooth)
        self._dy = lerp(self._dy, target_dy, dt_seconds, cfg.shake_smooth)
        return (self._dx, self._dy)
