"""Tests for python_plist helper (no macOS plist required)."""

from pathlib import Path

from ctimeli.adapters.macos import python_plist


def test_calendar_usage_present_when_plist_has_key(monkeypatch, tmp_path):
    plist = tmp_path / "Info.plist"
    plist.write_text("<?xml version=\"1.0\" encoding=\"UTF-8\"?><plist/>", encoding="utf-8")

    def fake_plist() -> Path:
        return plist

    calls: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        class R:
            returncode = 0

        return R()

    monkeypatch.setattr(python_plist, "python_framework_info_plist", fake_plist)
    monkeypatch.setattr(python_plist.subprocess, "run", fake_run)
    assert python_plist.calendar_usage_description_present() is True
    assert "NSCalendarsFullAccessUsageDescription" in calls[0][2]
