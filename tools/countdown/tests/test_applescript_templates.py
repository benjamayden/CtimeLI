"""Tests for adapters/macos/applescript_templates.py — runs on Linux (no PyObjC).

The templates module has no platform imports. All tests are table-driven and
verify that generated scripts contain bundle identifiers, never display names,
and that injection strings are filtered out.
"""

import pytest

from countdown.adapters.macos.applescript_templates import hide_script, minimize_script


# -- hide_script --------------------------------------------------------------

def test_hide_script_contains_bundle_id():
    script = hide_script(["com.google.Chrome"])
    assert script is not None
    assert 'bundle identifier is "com.google.Chrome"' in script


def test_hide_script_no_display_names():
    script = hide_script(["com.google.Chrome"])
    assert script is not None
    assert "Google Chrome" not in script


def test_hide_script_multiple_ids():
    script = hide_script(["com.foo", "com.bar"])
    assert script is not None
    assert 'bundle identifier is "com.foo"' in script
    assert 'bundle identifier is "com.bar"' in script


def test_hide_script_filters_invalid_ids():
    injection = 'com.evil" & do shell script "rm -rf ~'
    script = hide_script([injection, "com.safe"])
    assert script is not None
    assert injection not in script
    assert 'bundle identifier is "com.safe"' in script


def test_hide_script_all_invalid_returns_none():
    assert hide_script(['com.evil" injection']) is None


def test_hide_script_empty_returns_none():
    assert hide_script([]) is None


def test_hide_script_returns_count():
    script = hide_script(["com.foo"])
    assert script is not None
    assert "hideCount" in script
    assert "return hideCount" in script


# -- minimize_script ----------------------------------------------------------

def test_minimize_script_contains_bundle_id():
    script = minimize_script(["com.apple.Notes"])
    assert script is not None
    assert 'bundle identifier is "com.apple.Notes"' in script


def test_minimize_script_no_display_names():
    script = minimize_script(["com.apple.Notes"])
    assert script is not None
    assert "Notes" not in script.replace("com.apple.Notes", "")


def test_minimize_script_filters_invalid_ids():
    injection = 'com.bad" evil'
    script = minimize_script([injection, "com.good"])
    assert script is not None
    assert injection not in script
    assert 'bundle identifier is "com.good"' in script


def test_minimize_script_all_invalid_returns_none():
    assert minimize_script(['com.bad" evil']) is None


def test_minimize_script_empty_returns_none():
    assert minimize_script([]) is None


def test_minimize_script_returns_count():
    script = minimize_script(["com.foo"])
    assert script is not None
    assert "minCount" in script
    assert "return minCount" in script


# -- injection safety sanity check ------------------------------------------

@pytest.mark.parametrize("payload", [
    '"',
    '" & do shell script "rm -rf ~',
    "'; do shell script 'harm'",
    "\n tell application",
])
def test_injection_payloads_never_appear_in_hide_output(payload: str):
    # Payloads that would be dangerous if interpolated must never reach the script.
    script = hide_script([payload])
    if script is not None:
        assert payload not in script
