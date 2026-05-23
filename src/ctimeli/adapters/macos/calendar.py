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
        EKAuthorizationStatusDenied,
        EKAuthorizationStatusFullAccess,
        EKAuthorizationStatusNotDetermined,
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
    EKAuthorizationStatusNotDetermined = 0
    EKAuthorizationStatusDenied = 2

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
        self._denial_warned = False
        self._settings_opened = False
        self._access_failed = False

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
        if self._access_failed:
            return False

        self._store = EKEventStore.alloc().init()
        return self._apply_status(self._read_status(), request_if_needed=True)

    def access_granted(self) -> bool:
        """True when read access is already granted — never prompts."""
        if not _HAS_EVENTKIT:
            return False
        if self._access_ok:
            return True
        if self._access_failed:
            return False
        return self._read_status() in _READ_OK

    def recheck_access(self) -> bool:
        """Re-read TCC status after the user changes System Settings."""
        if not _HAS_EVENTKIT:
            return False
        self._access_failed = False
        self._denial_warned = False
        if self._store is None:
            self._store = EKEventStore.alloc().init()
        return self._apply_status(self._read_status(), request_if_needed=False)

    def _warn_denial(self, message: str) -> None:
        if self._denial_warned:
            return
        self._denial_warned = True
        self._logger.warn(message)

    def _read_status(self) -> int:
        return int(EKEventStore.authorizationStatusForEntityType_(EKEntityTypeEvent))

    def _apply_status(self, status: int, *, request_if_needed: bool) -> bool:
        if status in _READ_OK:
            self._access_ok = True
            return True
        if status == EKAuthorizationStatusWriteOnly:
            self._access_failed = True
            self._open_calendar_settings_once()
            self._warn_denial(
                "Calendar: Add Events Only — enable Full Access, or ./run permissions"
            )
            return False
        if request_if_needed and status == EKAuthorizationStatusNotDetermined:
            if not self._request_access():
                self._access_failed = True
                status = self._read_status()
                if status in _READ_OK:
                    self._access_ok = True
                    return True
                self._warn_denial(
                    "Calendar: click Allow on the Python calendars dialog, "
                    "or run ./run permissions"
                )
                return False
            self._access_ok = True
            return True
        if status == EKAuthorizationStatusDenied:
            self._access_failed = True
            self._open_calendar_settings_once()
            self._warn_denial(
                "Calendar access denied — System Settings → Calendars, or ./run permissions"
            )
            return False
        if status != EKAuthorizationStatusNotDetermined:
            self._access_failed = True
            self._open_calendar_settings_once()
        self._warn_denial(
            "Calendar access not available — run ./run permissions"
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
        import os

        from ctimeli.adapters.macos.permissions import activate_for_system_prompt
        from ctimeli.adapters.macos.python_plist import calendar_usage_description_present
        from ctimeli.adapters.macos.runloop import pump_run_loop

        if not calendar_usage_description_present():
            return False

        activate_for_system_prompt()
        watch_mode = os.environ.get("CTIMELI_WATCH_CHILD") == "1" or os.environ.get(
            "CTIMELI_WATCH_FOREGROUND"
        ) == "1"
        done = {"ok": False, "finished": False, "error": None}

        def completion(granted, error):
            done["ok"] = bool(granted)
            done["error"] = str(error) if error is not None else None
            done["finished"] = True

        if hasattr(self._store, "requestFullAccessToEventsWithCompletion_"):
            self._store.requestFullAccessToEventsWithCompletion_(completion)
        else:
            self._store.requestAccessToEntity_completion_(EKEntityTypeEvent, completion)

        if watch_mode:
            # AppHelper owns the run loop in watch — never nest pump_run_loop here.
            return False

        deadline = time.monotonic() + 120.0
        while not done["finished"] and time.monotonic() < deadline:
            pump_run_loop(0.1)
        if done["error"]:
            self._logger.warn(f"Calendar request error: {done['error']}")
        return done["ok"]

    def _open_calendar_settings_once(self) -> None:
        if self._settings_opened:
            return
        self._settings_opened = True
        from ctimeli.adapters.macos.permissions import open_calendar_settings

        open_calendar_settings()
        self._logger.info(
            "System Settings → Calendars opened. Enable Full Access, then ./run permissions"
        )


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
