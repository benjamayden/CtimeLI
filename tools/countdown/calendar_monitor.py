"""Calendar polling via EventKit (macOS)."""

from __future__ import annotations

import datetime as dt
import sys
import time
from dataclasses import dataclass

from config import AppConfig

try:
    from EventKit import (
        EKAuthorizationStatusAuthorized,
        EKAuthorizationStatusFullAccess,
        EKAuthorizationStatusWriteOnly,
        EKEntityTypeEvent,
        EKEventStore,
        EKParticipantStatusAccepted,
        EKParticipantStatusTentative,
        EKParticipantStatusUnknown,
    )

    _HAS_EVENTKIT = True
except ImportError:
    _HAS_EVENTKIT = False
    EKParticipantStatusAccepted = 2  # type: ignore[misc, assignment]
    EKParticipantStatusTentative = 4  # type: ignore[misc, assignment]
    EKParticipantStatusUnknown = 0  # type: ignore[misc, assignment]
    EKAuthorizationStatusAuthorized = 3  # type: ignore[misc, assignment]
    EKAuthorizationStatusFullAccess = 4  # type: ignore[misc, assignment]
    EKAuthorizationStatusWriteOnly = 5  # type: ignore[misc, assignment]


@dataclass(frozen=True)
class CalendarEvent:
    event_id: str
    title: str
    start: dt.datetime


def _nsdate_to_datetime(value) -> dt.datetime:
    return dt.datetime.fromtimestamp(value.timeIntervalSince1970())


def _datetime_to_nsdate(value: dt.datetime):
    import AppKit

    return AppKit.NSDate.dateWithTimeIntervalSince1970_(value.timestamp())


def _is_accepted(event) -> bool:
    attendees = event.attendees()
    if not attendees:
        return True
    organizer = event.organizer()
    if organizer is not None and organizer.isCurrentUser():
        return True
    for attendee in attendees:
        if attendee.isCurrentUser():
            status = attendee.participantStatus()
            return status in (
                EKParticipantStatusAccepted,
                EKParticipantStatusTentative,
                EKParticipantStatusUnknown,
            )
    return False


def _authorization_status() -> int | None:
    if not _HAS_EVENTKIT:
        return None
    return int(EKEventStore.authorizationStatusForEntityType_(EKEntityTypeEvent))


def _has_read_access(status: int | None = None) -> bool:
    if status is None:
        status = _authorization_status()
    if status is None:
        return False
    return status in (EKAuthorizationStatusAuthorized, EKAuthorizationStatusFullAccess)


class CalendarMonitor:
    def __init__(self, cfg: AppConfig) -> None:
        self.cfg = cfg
        self._store = None
        self._access_ok = False
        self._warned_no_eventkit = False

    def ensure_access(self) -> bool:
        if not self.cfg.calendar_enabled:
            return False
        if not _HAS_EVENTKIT:
            if not self._warned_no_eventkit:
                self._warned_no_eventkit = True
                print(
                    "Calendar disabled: install pyobjc-framework-EventKit",
                    file=sys.stderr,
                    flush=True,
                )
            return False
        if self._access_ok:
            return True
        self._store = EKEventStore.alloc().init()
        status = _authorization_status()
        if _has_read_access(status):
            self._access_ok = True
            return True
        if status == EKAuthorizationStatusWriteOnly:
            print(
                "Calendar has Add Events Only — enable Full Access in "
                "System Settings → Privacy & Security → Calendars",
                file=sys.stderr,
                flush=True,
            )
            return False
        granted = self._request_access()
        if granted or _has_read_access():
            self._access_ok = True
            return True
        print(
            "Calendar access denied — enable Full Access in "
            "System Settings → Privacy & Security → Calendars",
            file=sys.stderr,
            flush=True,
        )
        return False

    def _request_access(self) -> bool:
        done = {"ok": False, "finished": False}

        def completion(granted, _error):
            done["ok"] = bool(granted)
            done["finished"] = True

        if hasattr(self._store, "requestFullAccessToEventsWithCompletion_"):
            self._store.requestFullAccessToEventsWithCompletion_(completion)
        else:
            self._store.requestAccessToEntity_completion_(EKEntityTypeEvent, completion)

        import AppKit

        deadline = time.monotonic() + 120.0
        while not done["finished"] and time.monotonic() < deadline:
            ns_deadline = AppKit.NSDate.dateWithTimeIntervalSinceNow_(0.05)
            AppKit.NSRunLoop.currentRunLoop().runMode_beforeDate_(
                AppKit.NSDefaultRunLoopMode, ns_deadline
            )
        if done["finished"]:
            return done["ok"]
        return _has_read_access()

    def nearest_event_within(self, minutes: float | None = None) -> CalendarEvent | None:
        """Nearest accepted event starting within the next `minutes` (default from config)."""
        if not self.ensure_access() or self._store is None:
            return None
        window = minutes if minutes is not None else self.cfg.calendar_window_minutes
        now = dt.datetime.now()
        end = now + dt.timedelta(minutes=window)
        predicate = self._store.predicateForEventsWithStartDate_endDate_calendars_(
            _datetime_to_nsdate(now),
            _datetime_to_nsdate(end + dt.timedelta(hours=24)),
            None,
        )
        events = self._store.eventsMatchingPredicate_(predicate) or []
        nearest: CalendarEvent | None = None
        nearest_start: dt.datetime | None = None
        for event in events:
            if not _is_accepted(event):
                continue
            start = _nsdate_to_datetime(event.startDate())
            if start <= now or start > end:
                continue
            if nearest_start is None or start < nearest_start:
                event_id = event.eventIdentifier() or f"{event.title()}:{event.startDate()}"
                title = event.title() or "Event"
                nearest = CalendarEvent(event_id=event_id, title=title, start=start)
                nearest_start = start
        return nearest
