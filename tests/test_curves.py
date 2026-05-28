"""Tests for domain.curves — see docs/domain.md section 2."""

import pytest

from ctimeli.domain.config import AppConfig
from ctimeli.domain.curves import blur_intensity, pulse_opacity, pulse_spread

CFG = AppConfig()  # defaults: pulse window 120 s, ramp 10 s, max 0.85


def test_pulse_opacity_zero_outside_window():
    assert pulse_opacity(200.0, CFG) == 0.0
    assert pulse_opacity(120.0, CFG) == 0.0  # window edge, elapsed 0
    assert pulse_opacity(0.0, CFG) == 0.0  # at zero


def test_pulse_opacity_reaches_max_after_ramp():
    # elapsed == ramp (10 s) -> smoothstep(1) -> full max opacity.
    assert pulse_opacity(110.0, CFG) == pytest.approx(0.85)


def test_pulse_opacity_midpoint():
    # elapsed 5 s, u = 0.5, smoothstep(0.5) = 0.5.
    assert pulse_opacity(115.0, CFG) == pytest.approx(0.85 * 0.5)


def test_pulse_spread_zero_outside_window():
    assert pulse_spread(200.0, CFG) == 0.0
    assert pulse_spread(0.0, CFG) == 0.0


def test_pulse_spread_grows_over_window():
    assert pulse_spread(120.0, CFG) == pytest.approx(0.0)  # elapsed 0
    assert pulse_spread(1.0, CFG) == pytest.approx(119.0 / 120.0)  # near zero


def test_pulse_spread_ramp_power_is_applied():
    late = AppConfig(pulse_ramp_power=3.0)
    # elapsed 60 s of a 120 s window -> t = 0.5 -> 0.5**3 = 0.125.
    assert pulse_spread(60.0, late) == pytest.approx(0.125)


def test_blur_intensity_zero_outside_window():
    assert blur_intensity(200.0, CFG) == 0.0
    assert blur_intensity(60.0, CFG) == 0.0  # outside default 30 s blur window
    assert blur_intensity(31.0, CFG) == 0.0


def test_blur_intensity_full_at_zero():
    assert blur_intensity(0.0, CFG) == 1.0


def test_blur_uses_separate_window_from_glow():
    assert pulse_spread(60.0, CFG) > 0.0
    assert blur_intensity(60.0, CFG) == 0.0
    assert blur_intensity(15.0, CFG) > 0.0


def test_blur_intensity_ramp_power():
    late = AppConfig(blur_before_secs=30.0, pulse_ramp_power=3.0)
    # elapsed 15 s of a 30 s window -> t = 0.5 -> 0.125.
    assert blur_intensity(15.0, late) == pytest.approx(0.125)
