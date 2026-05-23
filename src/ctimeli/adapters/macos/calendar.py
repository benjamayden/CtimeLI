"""EventKitCalendar — the CalendarSource port via EventKit.

Supplies the nearest upcoming accepted event, normalised to a domain
CalendarEvent. See docs/ports.md and edge-cases.md "Unverified surface".
"""

from __future__ import annotations

import datetime as dt
import time

import AppKit

from ctimeli import ports
from ctimeli.domain.calendar import CalendarEvent, calendar_block_target, hard_stop_target
from ctimeli.domain.calendar_fields import parse_call_url, parse_room

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
except ImportError:  # pragma: no cover - macOS-only dependency
    _HAS_EVENTKIT = False
    EKParticipantStatusAccepted = 2
    EKParticipantStatusTentative = 4
    EKParticipantStatusUnknown = 0
    EKAuthorizationStatusAuthorized = 3
    EKAuthorizationStatusFullAccess = 4
    EKAuthorizationStatusWriteOnly = 5

_READ_OK = (EKAuthorizationStatusAuthorized, EKAuthorizationStatusFullAccess)
_ACCEPTED = (
    EKParticipantStatusAccepted,
    EKParticipantStatusTentative,
    EKParticipantStatusUnknown,
)


class EventKitCalendar:
    """EventKit-backed calendar source."""

    def __init__(self, logger: ports.Logger, *, store=None) -> None:
        self._logger = logger
        # An injected store (e.g. from a test) is treated as pre-authorized.
        self._store = store
        self._access_ok = store is not None
        self._warned = False

    def ensure_access(self) -> bool:
        if not _HAS_EVENTKIT:
            if not self._warned:
                self._warned = True
                self._logger.warn(
                    "Calendar disabled: install pyobjc-framework-EventKit"
                )
            return False
        if self._access_ok:
            return True

        self._store = EKEventStore.alloc().init()
        status = int(EKEventStore.authorizationStatusForEntityType_(EKEntityTypeEvent))
        if status in _READ_OK:
            self._access_ok = True
            return True
        if status == EKAuthorizationStatusWriteOnly:
            self._logger.warn(
                "Calendar has Add Events Only — enable Full Access in "
                "System Settings -> Privacy & Security -> Calendars"
            )
            return False
        if self._request_access():
            self._access_ok = True
            return True
        self._logger.warn(
            "Calendar access denied — enable Full Access in "
            "System Settings -> Privacy & Security -> Calendars"
        )
        return False

    def nearest_event_within(self, minutes: float) -> CalendarEvent | None:
        if not self.ensure_access() or self._store is None:
            return None
        now = dt.datetime.now()
        end = now + dt.timedelta(minutes=minutes)
        # Query a wider span than `end` so all-day / long events still match.
        predicate = self._store.predicateForEventsWithStartDate_endDate_calendars_(
            _to_nsdate(now), _to_nsdate(end + dt.timedelta(hours=24)), None
        )
        events = self._store.eventsMatchingPredicate_(predicate) or []

        nearest: CalendarEvent | None = None
        nearest_start: dt.datetime | None = None
        for event in events:
            if not _is_accepted(event):
                continue
            start = _from_nsdate(event.startDate())
            if start <= now or start > end:
                continue
            if nearest_start is None or start < nearest_start:
                event_id = event.eventIdentifier() or f"{event.title()}:{event.startDate()}"
                location = (event.location() or "").strip()
                notes = (event.notes() or "").strip()
                url_field = (event.URL() or "").strip() or None
                call_url = parse_call_url(url_field, location, notes)
                room = parse_room(location)
                nearest = CalendarEvent(
                    event_id=event_id,
                    title=event.title() or "Event",
                    start=start,
                    call_url=call_url,
                    room=room,
                )
                nearest_start = start
        return nearest

    def _request_access(self) -> bool:
        done = {"ok": False, "finished": False}

        def completion(granted, _error):
            done["ok"] = bool(granted)
            done["finished"] = True

        if hasattr(self._store, "requestFullAccessToEventsWithCompletion_"):
            self._store.requestFullAccessToEventsWithCompletion_(completion)
        else:
            self._store.requestAccessToEntity_completion_(EKEntityTypeEvent, completion)

        deadline = time.monotonic() + 120.0
        while not done["finished"] and time.monotonic() < deadline:
            AppKit.NSRunLoop.currentRunLoop().runMode_beforeDate_(
                AppKit.NSDefaultRunLoopMode,
                AppKit.NSDate.dateWithTimeIntervalSinceNow_(0.05),
            )
        return done["ok"]


def _to_nsdate(value: dt.datetime):
    return AppKit.NSDate.dateWithTimeIntervalSince1970_(value.timestamp())


def _from_nsdate(value) -> dt.datetime:
    return dt.datetime.fromtimestamp(value.timeIntervalSince1970())


def _is_accepted(event) -> bool:
    attendees = event.attendees()
    if not attendees:
        return True
    organizer = event.organizer()
    if organizer is not None and organizer.isCurrentUser():
        return True
    for attendee in attendees:
        if attendee.isCurrentUser():
            return attendee.participantStatus() in _ACCEPTED
    return False
