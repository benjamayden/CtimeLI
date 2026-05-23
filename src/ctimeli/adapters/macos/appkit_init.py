"""Safe NSApplication bootstrap for CLI use (edge-cases #45).

Never use ``ActivationPolicyRegular`` here — ``RegisterApplication`` aborts when
Python is spawned from Cursor's integrated terminal.
"""

from __future__ import annotations

import sys

import AppKit

_initialized = False


def ensure_appkit_initialized() -> None:
    """Idempotent AppKit init with accessory policy (safe from embedded terminals)."""
    global _initialized
    if "pytest" in sys.modules:
        return
    if _initialized:
        return
    app = AppKit.NSApplication.sharedApplication()
    app.setActivationPolicy_(AppKit.NSApplicationActivationPolicyAccessory)
    app.finishLaunching()
    _initialized = True
