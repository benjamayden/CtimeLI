"""Tests for domain.calendar_fields."""

import pytest

from countdown.domain.calendar_fields import parse_call_url, parse_room


@pytest.mark.parametrize(
    "text,expected",
    [
        ("https://zoom.us/j/123", "https://zoom.us/j/123"),
        ("Join at https://meet.google.com/abc-def", "https://meet.google.com/abc-def"),
        ("", None),
        (None, None),
    ],
)
def test_parse_call_url(text, expected):
    assert parse_call_url(text) == expected


def test_parse_call_url_prefers_first_field():
    assert parse_call_url("https://zoom.us/j/1", "https://zoom.us/j/2") == "https://zoom.us/j/1"


@pytest.mark.parametrize(
    "location,expected",
    [
        ("Room 4B", "Room 4B"),
        ("Building A — Conference", "Building A — Conference"),
        ("https://zoom.us/j/123", None),
        ("", None),
        (None, None),
    ],
)
def test_parse_room(location, expected):
    assert parse_room(location) == expected
