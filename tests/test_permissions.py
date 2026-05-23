"""Tests for macOS permission launch flow (fakes only — no AppKit)."""

from ctimeli.adapters.macos.permissions import (
    mark_permissions_setup_done,
    permissions_setup_needed,
    request_watch_launch_permissions,
    run_permissions_setup,
    setup_marker_path,
)
from ctimeli.domain.config import AppConfig

from .fakes import FakeCalendar, FakeWorkspaceTidy, RecordingLogger


def test_launch_permissions_skips_when_already_granted(monkeypatch, tmp_path):
    monkeypatch.setenv("CTIMELI_PERMISSIONS_MARKER", str(tmp_path / "setup"))
    mark_permissions_setup_done()
    monkeypatch.setattr(
        "ctimeli.adapters.macos.permissions.accessibility_granted",
        lambda: True,
    )
    tidy = FakeWorkspaceTidy()
    cal = FakeCalendar(access=True)
    cfg = AppConfig(block_on_end=True, calendar_enabled=True)
    logger = RecordingLogger()
    request_watch_launch_permissions(
        cfg, logger=logger, workspace_tidy=tidy, calendar=cal
    )
    assert tidy.access_calls == 0
    assert cal.access_calls == 0
    assert logger.info_lines == []


def test_launch_permissions_requests_accessibility_when_block_on_end(monkeypatch, tmp_path):
    monkeypatch.setenv("CTIMELI_PERMISSIONS_MARKER", str(tmp_path / "setup"))
    tidy = FakeWorkspaceTidy()
    cal = FakeCalendar()
    cfg = AppConfig(block_on_end=True, calendar_enabled=False)
    request_watch_launch_permissions(
        cfg, logger=RecordingLogger(), workspace_tidy=tidy, calendar=cal
    )
    assert tidy.access_calls >= 1
    assert cal.access_calls == 0
    assert setup_marker_path().exists()


def test_launch_permissions_requests_calendar_when_enabled(monkeypatch, tmp_path):
    monkeypatch.setenv("CTIMELI_PERMISSIONS_MARKER", str(tmp_path / "setup"))
    monkeypatch.setattr(
        "ctimeli.adapters.macos.permissions.ensure_calendar_dialog_ready",
        lambda _logger: True,
    )
    tidy = FakeWorkspaceTidy()
    cal = FakeCalendar()
    cfg = AppConfig(block_on_end=False, calendar_enabled=True)
    request_watch_launch_permissions(
        cfg, logger=RecordingLogger(), workspace_tidy=tidy, calendar=cal
    )
    assert tidy.access_calls == 0
    assert cal.access_calls == 1


def test_permissions_setup_needed_until_marker(monkeypatch, tmp_path):
    marker = tmp_path / "setup"
    monkeypatch.setenv("CTIMELI_PERMISSIONS_MARKER", str(marker))
    assert permissions_setup_needed() is True
    mark_permissions_setup_done()
    assert permissions_setup_needed() is False


def test_run_permissions_setup_includes_accessibility_for_cli(monkeypatch, tmp_path):
    monkeypatch.setenv("CTIMELI_PERMISSIONS_MARKER", str(tmp_path / "setup"))
    tidy = FakeWorkspaceTidy()
    cal = FakeCalendar()
    cfg = AppConfig(block_on_end=False, calendar_enabled=False)
    run_permissions_setup(
        cfg,
        logger=RecordingLogger(),
        workspace_tidy=tidy,
        calendar=cal,
        wait_for_user=True,
        include_accessibility=True,
    )
    assert tidy.access_calls >= 1
