"""Parse user time input into a target datetime. See docs/domain.md section 4.

Both functions take `now` as an explicit parameter — they never read the clock,
so they are deterministic and unit-testable (see edge-cases.md #4).
"""

from __future__ import annotations

import datetime as dt
import re

_TIME_RE = re.compile(
    r"^(\d{1,2})(?::(\d{2})(?::(\d{2}))?)?\s*(am|pm|a\.m\.|p\.m\.)?$",
    re.IGNORECASE,
)
_MINUTES_ONLY_RE = re.compile(r"^\d{1,4}$")
_DECIMAL_MINUTES_RE = re.compile(r"^\d+\.\d+$")


def parse_target_time(raw: str, now: dt.datetime) -> dt.datetime:
    """Parse a clock time ('6:00', '18:30', '7am') into its next occurrence.

    Raises ValueError on unparseable or out-of-range input.
    """
    match = _TIME_RE.match(raw.strip())
    if not match:
        raise ValueError(
            f"Could not parse time: {raw!r} (try 6:00, 18:00, or 6:00pm)"
        )

    hour = int(match.group(1))
    minute = int(match.group(2) or 0)
    second = int(match.group(3) or 0)
    meridiem = (match.group(4) or "").lower().replace(".", "")

    if minute >= 60 or second >= 60 or hour > 23:
        raise ValueError(f"Invalid time: {raw!r}")

    if meridiem in {"am", "pm"}:
        if hour < 1 or hour > 12:
            raise ValueError(f"Hour must be 1-12 with am/pm: {raw!r}")
        if meridiem == "pm" and hour != 12:
            hour += 12
        elif meridiem == "am" and hour == 12:
            hour = 0
        return _next_occurrence(now, hour, minute, second)

    if hour >= 13:
        # Unambiguous 24-hour time.
        return _next_occurrence(now, hour, minute, second)

    # Ambiguous: hour <= 12 with no meridiem — try both, pick the soonest.
    candidates = [
        _next_occurrence(now, h, minute, second)
        for h in {hour % 12, (hour % 12) + 12}
    ]
    return min(candidates, key=lambda t: t - now)


def parse_quick_input(raw: str, now: dt.datetime) -> dt.datetime:
    """Parse CLI / menu-bar input: bare digits are minutes, else clock time."""
    text = raw.strip()
    if not text:
        raise ValueError("Empty input")
    if _MINUTES_ONLY_RE.fullmatch(text):
        return now + dt.timedelta(minutes=int(text))
    if _DECIMAL_MINUTES_RE.fullmatch(text):
        return now + dt.timedelta(minutes=float(text))
    return parse_target_time(text, now)


def parse_clock_time(raw: str) -> dt.time:
    """Parse a clock-only time ('22:00', '6:30pm') into a time-of-day."""
    match = _TIME_RE.match(raw.strip())
    if not match:
        raise ValueError(
            f"Could not parse time: {raw!r} (try 22:00, 18:00, or 6:00pm)"
        )

    hour = int(match.group(1))
    minute = int(match.group(2) or 0)
    second = int(match.group(3) or 0)
    meridiem = (match.group(4) or "").lower().replace(".", "")

    if minute >= 60 or second >= 60 or hour > 23:
        raise ValueError(f"Invalid time: {raw!r}")

    if meridiem in {"am", "pm"}:
        if hour < 1 or hour > 12:
            raise ValueError(f"Hour must be 1-12 with am/pm: {raw!r}")
        if meridiem == "pm" and hour != 12:
            hour += 12
        elif meridiem == "am" and hour == 12:
            hour = 0
    elif hour >= 13:
        pass  # unambiguous 24-hour
    # else: hour <= 12 without meridiem — use as 24-hour clock (6:00 = 06:00)

    return dt.time(hour, minute, second)


def _next_occurrence(
    now: dt.datetime, hour: int, minute: int, second: int
) -> dt.datetime:
    """Today at h:m:s, rolled to tomorrow if that is already past."""
    target = now.replace(hour=hour, minute=minute, second=second, microsecond=0)
    if target <= now:
        target += dt.timedelta(days=1)
    return target
