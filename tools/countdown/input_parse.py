"""Parse quick-add timer input for watch mode and one-shot runs."""

from __future__ import annotations

import datetime as dt
import re

TIME_RE = re.compile(
    r"^(\d{1,2})(?::(\d{2})(?::(\d{2}))?)?\s*(am|pm|a\.m\.|p\.m\.)?$",
    re.IGNORECASE,
)

MINUTES_ONLY_RE = re.compile(r"^\d{1,4}$")
DECIMAL_MINUTES_RE = re.compile(r"^\d+\.\d+$")


def parse_target_time(raw: str) -> dt.datetime:
    """Parse a clock time into the next future datetime."""
    m = TIME_RE.match(raw.strip())
    if not m:
        raise ValueError(f"Could not parse time: {raw!r} (try 6:00, 18:00, or 6:00pm)")

    hour = int(m.group(1))
    minute = int(m.group(2) or 0)
    second = int(m.group(3) or 0)
    meridiem = (m.group(4) or "").lower().replace(".", "")

    if minute >= 60 or second >= 60 or hour > 23:
        raise ValueError(f"Invalid time: {raw!r}")

    now = dt.datetime.now()

    if meridiem in {"am", "pm"}:
        if hour < 1 or hour > 12:
            raise ValueError(f"Hour must be 1–12 with am/pm: {raw!r}")
        if meridiem == "pm" and hour != 12:
            hour += 12
        elif meridiem == "am" and hour == 12:
            hour = 0
        target = now.replace(hour=hour, minute=minute, second=second, microsecond=0)
        if target <= now:
            target += dt.timedelta(days=1)
        return target

    if hour >= 13:
        target = now.replace(hour=hour, minute=minute, second=second, microsecond=0)
        if target <= now:
            target += dt.timedelta(days=1)
        return target

    candidates: list[dt.datetime] = []
    for h in {hour % 12, (hour % 12) + 12}:
        t = now.replace(hour=h, minute=minute, second=second, microsecond=0)
        if t <= now:
            t += dt.timedelta(days=1)
        candidates.append(t)
    return min(candidates, key=lambda t: t - now)


def parse_quick_input(raw: str) -> dt.datetime:
    """Watch-mode input: bare digits = minutes; otherwise clock time."""
    s = raw.strip()
    if not s:
        raise ValueError("Empty input")
    if MINUTES_ONLY_RE.fullmatch(s):
        return dt.datetime.now() + dt.timedelta(minutes=int(s))
    if DECIMAL_MINUTES_RE.fullmatch(s):
        return dt.datetime.now() + dt.timedelta(minutes=float(s))
    return parse_target_time(s)
