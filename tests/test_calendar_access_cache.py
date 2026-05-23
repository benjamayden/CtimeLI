"""Tests for EventKitCalendar access caching."""

from unittest.mock import patch

import pytest

from ctimeli.terminal_ui import skip
from tests.fakes import RecordingLogger


@pytest.mark.skipif(
    __import__("sys").platform != "darwin", reason="requires EventKit"
)
def test_ensure_access_does_not_re_request_after_failure():
    from EventKit import EKAuthorizationStatusNotDetermined, EKEntityTypeEvent

    from ctimeli.adapters.macos.calendar import EventKitCalendar

    cal = EventKitCalendar(logger=RecordingLogger())
    with patch.object(
        cal,
        "_read_status",
        return_value=EKAuthorizationStatusNotDetermined,
    ), patch.object(cal, "_request_access", return_value=False) as request:
        assert cal.ensure_access() is False
        assert cal.ensure_access() is False
    assert request.call_count == 1


def test_warn_denial_logs_once():
    from ctimeli.adapters.macos.calendar import EventKitCalendar

    logger = RecordingLogger()
    cal = EventKitCalendar(logger=logger)
    cal._warn_denial(skip("Calendar access was denied."))
    cal._warn_denial(skip("Calendar access was denied."))
    assert logger.warn_lines == [skip("Calendar access was denied.")]
