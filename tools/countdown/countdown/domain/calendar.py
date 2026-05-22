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

    Normally fires `calendar_block_before_mins` before the event. If that
    buffer has already passed but the event hasn't started, fires to the event
    start itself. Returns None only if the event has already started.
    """
    block_at = event_start - dt.timedelta(minutes=cfg.calendar_block_before_mins)
    if block_at > now:
        return block_at
    if event_start > now:
        return event_start  # buffer passed but event hasn't started — count to event
    return None
