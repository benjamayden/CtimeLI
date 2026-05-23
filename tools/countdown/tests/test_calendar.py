"""Tests for domain.calendar — see docs/domain.md section 5."""

import datetime as dt

from countdown.domain.calendar import (
    CalendarEvent,
    calendar_block_target,
    hard_stop_stroke_base,
    hard_stop_target,
    is_work_wifi,
)
from countdown.domain.config import AppConfig

NOW = dt.datetime(2026, 5, 21, 14, 30, 0)
CFG = AppConfig()  # calendar_block_before_mins default 7


def test_block_target_is_before_the_event():
    event_start = NOW + dt.timedelta(minutes=20)
    block_at = calendar_block_target(event_start, CFG, NOW)
    assert block_at == event_start - dt.timedelta(minutes=7)


def test_late_start_returns_event_start():
    # Event in 5 min, block fires 7 min before → block_at is 2 min ago.
    event_start = NOW + dt.timedelta(minutes=5)
    result = calendar_block_target(event_start, CFG, NOW)
    assert result == event_start


def test_late_start_buffer_fully_elapsed():
    # Event in 3 min, block fires 7 min before → block_at is 4 min ago.
    event_start = NOW + dt.timedelta(minutes=3)
    result = calendar_block_target(event_start, CFG, NOW)
    assert result == event_start


def test_block_target_at_boundary_returns_event_start():
    # block_at exactly == now: still a late start, count to event itself.
    event_start = NOW + dt.timedelta(minutes=7)
    result = calendar_block_target(event_start, CFG, NOW)
    assert result == event_start


def test_returns_none_when_event_already_started():
    event_start = NOW - dt.timedelta(minutes=1)
    assert calendar_block_target(event_start, CFG, NOW) is None


def test_returns_none_when_event_starts_exactly_now():
    assert calendar_block_target(NOW, CFG, NOW) is None


def test_calendar_event_optional_fields():
    event = CalendarEvent("id", "Standup", NOW, call_url="https://zoom.us/j/1", room="3A")
    assert event.call_url.endswith("/1")
    assert event.room == "3A"


def test_hard_stop_target_inside_warning_window():
    cfg = AppConfig(
        hard_stop_enabled=True,
        hard_stop_time=dt.time(22, 0),
        hard_stop_warning_mins=30.0,
    )
    now = dt.datetime(2026, 5, 21, 21, 45, 0)
    assert hard_stop_target(cfg, now) == dt.datetime(2026, 5, 21, 22, 0, 0)


def test_hard_stop_target_before_window_is_none():
    cfg = AppConfig(
        hard_stop_enabled=True,
        hard_stop_time=dt.time(22, 0),
        hard_stop_warning_mins=30.0,
    )
    now = dt.datetime(2026, 5, 21, 21, 29, 0)
    assert hard_stop_target(cfg, now) is None


def test_hard_stop_target_after_stop_is_none():
    cfg = AppConfig(
        hard_stop_enabled=True,
        hard_stop_time=dt.time(22, 0),
        hard_stop_warning_mins=30.0,
    )
    now = dt.datetime(2026, 5, 21, 22, 1, 0)
    assert hard_stop_target(cfg, now) is None


def test_hard_stop_target_disabled_is_none():
    cfg = AppConfig(hard_stop_enabled=False)
    assert hard_stop_target(cfg, NOW) is None


def test_hard_stop_stroke_base():
    cfg = AppConfig(hard_stop_stroke_r=0.95, hard_stop_stroke_g=0.55, hard_stop_stroke_b=0.15)
    rgb = hard_stop_stroke_base(cfg)
    assert rgb.r == 0.95


def test_is_work_wifi():
    ssids = frozenset({"Office", "Guest"})
    assert is_work_wifi("Office", ssids) is True
    assert is_work_wifi("Home", ssids) is False
    assert is_work_wifi(None, ssids) is False
