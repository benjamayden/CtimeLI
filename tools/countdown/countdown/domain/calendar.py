"""Calendar value type and block-target maths. See docs/domain.md section 5."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from .config import AppConfig


@dataclass(frozen=True)
class CalendarEvent:
    """An upcoming calendar event, normalised away from any platform type."""

    event_id: str
    title: str
    start: dt.datetime


def calendar_block_target(
    event_start: dt.datetime, cfg: AppConfig, now: dt.datetime
) -> dt.datetime | None:
    """When the countdown should hit zero for an event.

    The block fires `calendar_block_before_mins` before the event, leaving a
    buffer to arrive. Returns None if that moment is already past.
    """
    block_at = event_start - dt.timedelta(minutes=cfg.calendar_block_before_mins)
    if block_at <= now:
        return None
    return block_at
