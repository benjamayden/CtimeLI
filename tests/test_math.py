"""Tests for domain.math — see docs/domain.md section 1."""

import math

import pytest

from ctimeli.domain.math import clamp, format_duration, lerp, smoothstep


def test_clamp_bounds():
    assert clamp(5, 0, 10) == 5
    assert clamp(-1, 0, 10) == 0
    assert clamp(99, 0, 10) == 10


@pytest.mark.parametrize(
    "t,expected",
    [(-1.0, 0.0), (0.0, 0.0), (0.5, 0.5), (1.0, 1.0), (2.0, 1.0)],
)
def test_smoothstep_endpoints_and_clamp(t, expected):
    assert smoothstep(t) == pytest.approx(expected)


def test_smoothstep_is_monotonic():
    values = [smoothstep(i / 20) for i in range(21)]
    assert values == sorted(values)


def test_lerp_is_frame_rate_independent():
    # One step of dt=1 must equal two steps of dt=0.5 (the exp form guarantees it).
    rate = 3.0
    one_step = lerp(0.0, 10.0, 1.0, rate)
    half = lerp(0.0, 10.0, 0.5, rate)
    two_steps = lerp(half, 10.0, 0.5, rate)
    assert one_step == pytest.approx(two_steps)


def test_lerp_converges_toward_target():
    current = 0.0
    for _ in range(1000):
        current = lerp(current, 10.0, 1 / 60, 9.0)
    assert current == pytest.approx(10.0, abs=1e-6)


def test_lerp_zero_dt_is_a_no_op():
    assert lerp(3.0, 10.0, 0.0, 9.0) == 3.0


@pytest.mark.parametrize(
    "seconds,expected",
    [
        (0, "0s"),
        (-5, "0s"),
        (9, "9s"),
        (64, "1m 4s"),
        (60, "1m 0s"),
        (3725, "1h 2m 5s"),
        (3600, "1h 0m 0s"),
        (9.9, "9s"),
    ],
)
def test_format_duration(seconds, expected):
    assert format_duration(seconds) == expected
