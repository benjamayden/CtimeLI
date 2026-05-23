"""Stroke colours and the red-zone blend. See docs/domain.md section 3."""

from __future__ import annotations

from dataclasses import dataclass

from .math import smoothstep


@dataclass(frozen=True)
class RGB:
    """An immutable colour, each channel in [0, 1]."""

    r: float
    g: float
    b: float


STROKE_BLUE = RGB(0.20, 0.75, 1.00)
STROKE_RED = RGB(1.00, 0.12, 0.12)


def stroke_color_for_fraction(fraction: float, red_zone: float, base: RGB) -> RGB:
    """Blend `base` toward red as the stroke runs into the red zone.

    Above `red_zone` remaining the colour is `base`; at zero it is fully red;
    between, a per-channel linear blend gated by smoothstep.
    """
    if fraction > red_zone:
        return base
    # red_zone comes from config (a system boundary); guard a zero divisor.
    zone = max(red_zone, 1e-9)
    t = smoothstep(1.0 - fraction / zone)
    return RGB(
        base.r + t * (STROKE_RED.r - base.r),
        base.g + t * (STROKE_RED.g - base.g),
        base.b + t * (STROKE_RED.b - base.b),
    )
