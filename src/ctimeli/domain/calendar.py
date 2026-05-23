"""Calendar value type and block-target maths. See docs/domain.md section 5."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from .colors import RGB
from .config import AppConfig


@dataclass(frozen=True)
class CalendarEvent:
    """An upcoming calendar event, normalised away from any platform type."""

    event_id: str
    title: str
    start: dt.datetime
    call_url: str | None = None
    room: str | None = None


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


def hard_stop_target(cfg: AppConfig, now: dt.datetime) -> dt.datetime | None:
    """Return today's hard-stop datetime when inside the warning window.

    Window is (hard_stop - warning_mins, hard_stop]. Returns None when disabled,
    before the window opens, or after hard_stop has passed today.
    """
    if not cfg.hard_stop_enabled:
        return None
    stop_at = now.replace(
        hour=cfg.hard_stop_time.hour,
        minute=cfg.hard_stop_time.minute,
        second=cfg.hard_stop_time.second,
        microsecond=0,
    )
    window_start = stop_at - dt.timedelta(minutes=cfg.hard_stop_warning_mins)
    if now <= window_start or now > stop_at:
        return None
    return stop_at


def hard_stop_stroke_base(cfg: AppConfig) -> RGB:
    """Stroke base colour for hard-stop sessions."""
    return RGB(cfg.hard_stop_stroke_r, cfg.hard_stop_stroke_g, cfg.hard_stop_stroke_b)


def is_work_wifi(ssid: str | None, work_ssids: frozenset[str]) -> bool:
    """True when connected to a configured work SSID."""
    return ssid is not None and ssid in work_ssids
