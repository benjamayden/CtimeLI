"""Tests for embedded-terminal permission relaunch."""

from ctimeli.adapters.macos import permissions


def test_embedded_terminal_detects_cursor(monkeypatch):
    monkeypatch.setenv("TERM_PROGRAM", "cursor")
    assert permissions._embedded_terminal() is True


def test_should_not_relaunch_when_flag_set(monkeypatch):
    monkeypatch.setenv("CTIMELI_PERMISSIONS_IN_TERMINAL", "1")
    monkeypatch.setenv("TERM_PROGRAM", "cursor")
    assert permissions.should_relaunch_permissions_in_terminal() is False


def test_should_not_relaunch_in_terminal_app(monkeypatch):
    monkeypatch.delenv("CTIMELI_PERMISSIONS_IN_TERMINAL", raising=False)
    monkeypatch.setenv("TERM_PROGRAM", "Apple_Terminal")
    assert permissions._embedded_terminal() is False
