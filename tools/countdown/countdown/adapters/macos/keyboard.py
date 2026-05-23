"""Synthetic keyboard shortcuts for workspace tidy — macOS only.

US ANSI physical key codes; same positions on most keyboard layouts.
See docs/edge-cases.md and docs/features.md §8.
"""

from __future__ import annotations

# US ANSI physical key codes.
KEY_H = 4
KEY_M = 46

# Quartz kCGEventFlagMask* values.
FLAG_COMMAND = 0x100000
FLAG_ALTERNATE = 0x80000

HIDE_OTHERS_FLAGS = FLAG_COMMAND | FLAG_ALTERNATE
MINIMIZE_FLAGS = FLAG_COMMAND


def post_shortcut(key_code: int, flags: int) -> bool:
    """Post a key-down/key-up chord to the HID event tap. Returns True on success."""
    import Quartz

    down = Quartz.CGEventCreateKeyboardEvent(None, key_code, True)
    Quartz.CGEventSetFlags(down, flags)
    up = Quartz.CGEventCreateKeyboardEvent(None, key_code, False)
    Quartz.CGEventSetFlags(up, flags)
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, down)
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, up)
    return True
