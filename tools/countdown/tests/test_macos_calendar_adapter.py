"""Integration tests for adapters/macos/calendar.py — macOS + EventKit only.

Skipped automatically on Linux CI. On macOS, this creates a real calendar event,
queries the EventKitCalendar adapter, and cleans up. It exercises the acceptance
filter and time-window logic that FakeCalendar cannot reach.
"""

import datetime as dt
import sys

import pytest

pytestmark = pytest.mark.skipif(
    sys.platform != "darwin", reason="requires macOS EventKit"
)


def _get_authorized_store():
    """Return an EKEventStore with read access, or None if unavailable."""
    try:
        from EventKit import (
            EKAuthorizationStatusAuthorized,
            EKAuthorizationStatusFullAccess,
            EKEntityTypeEvent,
            EKEventStore,
        )
    except ImportError:
        return None

    store = EKEventStore.alloc().init()
    status = int(EKEventStore.authorizationStatusForEntityType_(EKEntityTypeEvent))
    read_ok = (EKAuthorizationStatusAuthorized, EKAuthorizationStatusFullAccess)
    if status not in read_ok:
        return None
    return store


def test_nearest_event_found():
    """Adapter finds a test event created in the default calendar."""
    store = _get_authorized_store()
    if store is None:
        pytest.skip("Calendar access not granted or EventKit unavailable")

    from EventKit import EKEvent, EKSpanThisEvent
    import AppKit

    from countdown.adapters.macos.calendar import EventKitCalendar
    from tests.fakes import RecordingLogger

    now = dt.datetime.now()
    start = now + dt.timedelta(minutes=5)
    end = start + dt.timedelta(minutes=30)

    ns_start = AppKit.NSDate.dateWithTimeIntervalSince1970_(start.timestamp())
    ns_end = AppKit.NSDate.dateWithTimeIntervalSince1970_(end.timestamp())

    event = EKEvent.eventWithEventStore_(store)
    event.setTitle_("__countdown_test_event__")
    event.setStartDate_(ns_start)
    event.setEndDate_(ns_end)
    event.setCalendar_(store.defaultCalendarForNewEvents())
    store.saveEvent_span_error_(event, EKSpanThisEvent, None)
    event_id = str(event.eventIdentifier())

    try:
        cal = EventKitCalendar(logger=RecordingLogger(), store=store)
        assert cal.ensure_access() is True
        result = cal.nearest_event_within(minutes=10)
        assert result is not None
        assert result.event_id == event_id
        assert result.title == "__countdown_test_event__"
    finally:
        store.removeEvent_span_error_(event, EKSpanThisEvent, None)


def test_past_event_not_returned():
    """An event that has already started is not returned by nearest_event_within."""
    store = _get_authorized_store()
    if store is None:
        pytest.skip("Calendar access not granted or EventKit unavailable")

    from EventKit import EKEvent, EKSpanThisEvent
    import AppKit

    from countdown.adapters.macos.calendar import EventKitCalendar
    from tests.fakes import RecordingLogger

    now = dt.datetime.now()
    # Event started 5 minutes ago
    start = now - dt.timedelta(minutes=5)
    end = now + dt.timedelta(minutes=25)

    ns_start = AppKit.NSDate.dateWithTimeIntervalSince1970_(start.timestamp())
    ns_end = AppKit.NSDate.dateWithTimeIntervalSince1970_(end.timestamp())

    event = EKEvent.eventWithEventStore_(store)
    event.setTitle_("__countdown_past_event__")
    event.setStartDate_(ns_start)
    event.setEndDate_(ns_end)
    event.setCalendar_(store.defaultCalendarForNewEvents())
    store.saveEvent_span_error_(event, EKSpanThisEvent, None)

    try:
        cal = EventKitCalendar(logger=RecordingLogger(), store=store)
        result = cal.nearest_event_within(minutes=10)
        # This event started in the past — it must not be returned.
        if result is not None:
            assert result.title != "__countdown_past_event__"
    finally:
        store.removeEvent_span_error_(event, EKSpanThisEvent, None)
