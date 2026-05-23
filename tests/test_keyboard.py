"""Tests for keyboard shortcut constants — runs on Linux (no PyObjC)."""

from ctimeli.adapters.macos import keyboard


def test_hide_others_uses_h_with_command_and_option():
    assert keyboard.KEY_H == 4
    assert keyboard.FLAG_COMMAND == 0x100000
    assert keyboard.FLAG_ALTERNATE == 0x80000
    assert keyboard.HIDE_OTHERS_FLAGS == keyboard.FLAG_COMMAND | keyboard.FLAG_ALTERNATE


def test_minimize_uses_m_with_command_only():
    assert keyboard.KEY_M == 46
    assert keyboard.MINIMIZE_FLAGS == keyboard.FLAG_COMMAND
