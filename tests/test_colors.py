"""Tests for domain.colors — see docs/domain.md section 3."""

import pytest

from ctimeli.domain.colors import STROKE_BLUE, STROKE_RED, stroke_color_for_fraction


def test_above_red_zone_is_base():
    assert stroke_color_for_fraction(0.5, 0.05, STROKE_BLUE) == STROKE_BLUE


def test_at_red_zone_edge_is_base():
    # fraction == red_zone is not strictly greater -> t = smoothstep(0) = 0.
    assert stroke_color_for_fraction(0.05, 0.05, STROKE_BLUE) == STROKE_BLUE


def test_at_zero_is_fully_red():
    result = stroke_color_for_fraction(0.0, 0.05, STROKE_BLUE)
    assert result.r == pytest.approx(STROKE_RED.r)
    assert result.g == pytest.approx(STROKE_RED.g)
    assert result.b == pytest.approx(STROKE_RED.b)


def test_midpoint_is_a_blend():
    # fraction 0.025 -> t = smoothstep(0.5) = 0.5 -> halfway blend.
    result = stroke_color_for_fraction(0.025, 0.05, STROKE_BLUE)
    assert result.r == pytest.approx((STROKE_BLUE.r + STROKE_RED.r) / 2)


def test_zero_red_zone_does_not_crash():
    # red_zone comes from config (a boundary); a 0 must not divide-by-zero.
    result = stroke_color_for_fraction(0.0, 0.0, STROKE_BLUE)
    assert result.r == pytest.approx(STROKE_RED.r)
