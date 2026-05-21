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


def test_block_target_is_none_when_already_past():
    # Event in 5 min, block fires 7 min before -> block_at is 2 min ago.
    event_start = NOW + dt.timedelta(minutes=5)
    assert calendar_block_target(event_start, CFG, NOW) is None


def test_block_target_none_at_exact_boundary():
    # block_at exactly == now must be skipped (<=).
    event_start = NOW + dt.timedelta(minutes=7)
    assert calendar_block_target(event_start, CFG, NOW) is None
