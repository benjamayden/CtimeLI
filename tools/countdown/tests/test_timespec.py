"""Tests for domain.timespec — the parsing table in docs/domain.md section 4."""

import datetime as dt

import pytest

from countdown.domain.timespec import parse_quick_input, parse_target_time

NOW = dt.datetime(2026, 5, 21, 14, 30, 0)  # a Thursday afternoon


def test_bare_digits_are_minutes():
    assert parse_quick_input("6", NOW) == NOW + dt.timedelta(minutes=6)
    assert parse_quick_input("90", NOW) == NOW + dt.timedelta(minutes=90)
    assert parse_quick_input("9999", NOW) == NOW + dt.timedelta(minutes=9999)


def test_decimal_minutes():
    assert parse_quick_input("0.5", NOW) == NOW + dt.timedelta(seconds=30)
    assert parse_quick_input("2.5", NOW) == NOW + dt.timedelta(minutes=2.5)


def test_ambiguous_hour_picks_nearest_future():
    # 6:00 -> 18:00 today (sooner than 06:00 tomorrow).
    result = parse_quick_input("6:00", NOW)
    assert (result.hour, result.day) == (18, 21)


def test_unambiguous_24h_hour():
    result = parse_quick_input("18:00", NOW)
    assert (result.hour, result.day) == (18, 21)


def test_twelve_oclock_is_ambiguous_noon_or_midnight():
    # 12 % 12 == 0 -> candidates {0, 12}; midnight tomorrow is nearest.
    result = parse_quick_input("12:00", NOW)
    assert (result.hour, result.minute, result.day) == (0, 0, 22)


def test_zero_hour_is_ambiguous():
    result = parse_quick_input("0:30", NOW)
    assert (result.hour, result.minute, result.day) == (0, 30, 22)


def test_meridiem_forces_interpretation():
    assert parse_target_time("6:00pm", NOW).hour == 18
    assert parse_target_time("7am", NOW).hour == 7
    assert parse_target_time("12am", NOW).hour == 0
    assert parse_target_time("12pm", NOW).hour == 12


def test_seconds_are_parsed():
    result = parse_target_time("9:05:30", NOW)
    assert (result.hour, result.minute, result.second) == (21, 5, 30)


@pytest.mark.parametrize("bad", ["13:00pm", "6:60", "9:00:99", "25:00", "5.", ".5", "soon"])
def test_invalid_input_raises(bad):
    with pytest.raises(ValueError):
        parse_target_time(bad, NOW)


def test_24h_time_rolls_to_tomorrow_when_past():
    # A 24-hour clock time that has already passed today must roll to tomorrow.
    now_evening = dt.datetime(2026, 5, 21, 19, 0, 0)
    result = parse_target_time("18:00", now_evening)
    assert result.day == 22
    assert result.hour == 18


def test_meridiem_past_time_rolls_to_tomorrow():
    # 7am has already passed at 14:30; the existing test only checks hour, not day.
    result = parse_target_time("7am", NOW)
    assert result.day == 22
    assert result.hour == 7


def test_empty_quick_input_raises():
    with pytest.raises(ValueError, match="Empty input"):
        parse_quick_input("", NOW)
