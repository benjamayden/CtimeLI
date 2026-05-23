"""Pure helpers for parsing calendar event metadata. See docs/domain.md section 5."""

from __future__ import annotations

import re

_URL_RE = re.compile(r'https?://[^\s<>"\']+', re.IGNORECASE)
_MEETING_HOSTS = ("zoom.us", "meet.google.com", "teams.microsoft.com", "webex.com")


def parse_call_url(*texts: str | None) -> str | None:
    """Extract the first meeting URL from EventKit URL, location, or notes."""
    for text in texts:
        if not text:
            continue
        stripped = text.strip()
        if stripped.lower().startswith("http"):
            return stripped
        match = _URL_RE.search(text)
        if match is not None:
            return match.group(0)
    return None


def parse_room(location: str | None) -> str | None:
    """Return a physical room name when location is not URL-like."""
    if not location or not location.strip():
        return None
    loc = location.strip()
    if loc.lower().startswith("http"):
        return None
    if _URL_RE.search(loc):
        return None
    lower = loc.lower()
    if any(host in lower for host in _MEETING_HOSTS):
        return None
    return loc
