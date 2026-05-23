"""Tests for scannable terminal copy helpers."""

from ctimeli.terminal_ui import ok, section, skip, tagged, warn


def test_tagged_fixed_width_column():
    line = tagged("OK", "Done.")
    assert line.startswith("OK    ")
    assert line.endswith("Done.")


def test_section_adds_blank_lines_and_uppercase():
    assert section("permissions") == ["", "PERMISSIONS", ""]


def test_status_helpers_use_distinct_tags():
    assert ok("x").startswith("OK")
    assert skip("x").startswith("SKIP")
    assert warn("x").startswith("!")
