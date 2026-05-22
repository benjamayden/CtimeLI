"""Tests for domain.calendar — see docs/domain.md section 5."""

import datetime as dt

from countdown.domain.calendar import calendar_block_target
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
