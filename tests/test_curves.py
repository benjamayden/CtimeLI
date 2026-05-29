"""Tests for domain.curves — see docs/domain.md section 2."""

import pytest

from ctimeli.domain.config import AppConfig
from ctimeli.domain.curves import blur_intensity, pulse_opacity, pulse_spread

CFG = AppConfig()  # defaults: pulse window 13.333%, ramp 1.111%, max 0.85


def test_pulse_opacity_zero_outside_window():
    assert pulse_opacity(0.5, CFG) == 0.0
    assert pulse_opacity(0.13333333333333333, CFG) == 0.0  # window edge, elapsed 0
    assert pulse_opacity(0.0, CFG) == 0.0  # at zero


def test_pulse_opacity_reaches_max_after_ramp():
    # elapsed == ramp -> smoothstep(1) -> full max opacity.
    assert pulse_opacity(0.12222222222222223, CFG) == pytest.approx(0.85)


def test_pulse_opacity_midpoint():
    # elapsed halfway through the ramp -> smoothstep(0.5) = 0.5.
    assert pulse_opacity(0.12777777777777777, CFG) == pytest.approx(0.85 * 0.5)


def test_pulse_spread_zero_outside_window():
    assert pulse_spread(0.5, CFG) == 0.0
    assert pulse_spread(0.0, CFG) == 0.0


def test_pulse_spread_grows_over_window():
    assert pulse_spread(0.13333333333333333, CFG) == pytest.approx(0.0)  # elapsed 0
    assert pulse_spread(0.01, CFG) == pytest.approx(0.925)  # near zero


def test_pulse_spread_ramp_power_is_applied():
    late = AppConfig(pulse_before_fraction=0.2, pulse_ramp_power=3.0)
    # elapsed halfway through a 20% window -> t = 0.5 -> 0.5**3 = 0.125.
    assert pulse_spread(0.1, late) == pytest.approx(0.125)


def test_blur_intensity_zero_outside_window():
    assert blur_intensity(0.5, CFG) == 0.0
    assert blur_intensity(0.1, CFG) == 0.0  # outside default 3.333% blur window
    assert blur_intensity(0.04, CFG) == 0.0


def test_blur_intensity_full_at_zero():
    assert blur_intensity(0.0, CFG) == 1.0


def test_blur_uses_separate_window_from_glow():
    assert pulse_spread(0.08, CFG) > 0.0
    assert blur_intensity(0.08, CFG) == 0.0
    assert blur_intensity(0.02, CFG) > 0.0


def test_blur_intensity_ramp_power():
    late = AppConfig(blur_before_fraction=0.1, pulse_ramp_power=3.0)
    # elapsed halfway through a 10% window -> t = 0.5 -> 0.125.
    assert blur_intensity(0.05, late) == pytest.approx(0.125)
