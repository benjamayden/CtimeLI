"""Tests for domain.curves — see docs/domain.md section 2."""

import pytest

from countdown.domain.config import AppConfig
from countdown.domain.curves import pulse_opacity, pulse_spread, shake_intensity

CFG = AppConfig()  # defaults: pulse window 120 s, ramp 10 s, max 0.85, wiggle 3 s


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


def test_shake_intensity_window():
    assert shake_intensity(5.0, CFG) == 0.0  # before the 3 s window
    assert shake_intensity(3.0, CFG) == pytest.approx(0.0)  # window edge
    assert shake_intensity(1.5, CFG) == pytest.approx(0.5)  # smoothstep(0.5)
    assert shake_intensity(0.0, CFG) == 0.0  # at zero


def test_shake_intensity_rises_toward_zero():
    assert shake_intensity(0.3, CFG) > shake_intensity(2.0, CFG)
