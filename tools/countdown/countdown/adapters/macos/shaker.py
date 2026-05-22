"""MacShaker — the WindowShaker port via the Accessibility API.

Moves the frontmost window to (original + offset) and always restores it. The
offset itself is computed by the pure domain.shake.ShakeMotion; this adapter
only carries it out. See docs/ports.md and edge-cases.md "Unverified surface".
"""

from __future__ import annotations

import AppKit

from countdown import ports

try:
    from ApplicationServices import (
        AXUIElementCopyAttributeValue,
        AXUIElementCreateApplication,
        AXUIElementSetAttributeValue,
        AXValueCreate,
        AXValueGetValue,
        kAXValueCGPointType,
    )

    _HAS_ACCESSIBILITY = True
except ImportError:  # pragma: no cover - macOS-only dependency
    _HAS_ACCESSIBILITY = False


class MacShaker:
    """Accessibility-driven frontmost-window shaker."""

    def __init__(
        self, logger: ports.Logger, skip_apps: frozenset[str] = frozenset()
    ) -> None:
        self._logger = logger
        # Apps never wiggled — the host terminal, system UI (docs/configuration.md).
        self._skip = frozenset(name.lower() for name in skip_apps)
        self._enabled = _HAS_ACCESSIBILITY
        self._ax_window = None
        self._ax_origin: AppKit.NSPoint | None = None
        self._warned_no_access = False
        self._warned_no_target = False

    def available(self) -> bool:
        return _HAS_ACCESSIBILITY and self._enabled

    def apply(self, dx: float, dy: float) -> bool:
        if not _HAS_ACCESSIBILITY:
            if not self._warned_no_access:
                self._warned_no_access = True
                self._logger.warn(
                    "Shake disabled: install pyobjc-framework-ApplicationServices"
                )
            return False
        if not self._enabled:
            return False

        if self._frontmost_is_skipped():
            return False

        window = self._focused_window()
        if window is None:
            if not self._warned_no_target:
                self._warned_no_target = True
                self._logger.warn(
                    "Shake: no focused window — click the app you want nudged."
                )
            return False

        if window != self._ax_window:
            self.restore()
            self._ax_window = window
            self._ax_origin = self._window_position(window)
        if self._ax_origin is None:
            return False

        point = AppKit.NSPoint(self._ax_origin.x + dx, self._ax_origin.y + dy)
        if not self._move_window(window, point):
            self._enabled = False
            self._logger.warn(
                "Shake disabled: allow Accessibility for this terminal in "
                "System Settings -> Privacy & Security -> Accessibility."
            )
            self.restore()
            return False
        return True

    def restore(self) -> None:
        if (
            _HAS_ACCESSIBILITY
            and self._ax_window is not None
            and self._ax_origin is not None
        ):
            value = AXValueCreate(kAXValueCGPointType, self._ax_origin)
            AXUIElementSetAttributeValue(self._ax_window, "AXPosition", value)
        self._ax_window = None
        self._ax_origin = None

    # -- Accessibility plumbing ---------------------------------------------

    def _frontmost_is_skipped(self) -> bool:
        app = AppKit.NSWorkspace.sharedWorkspace().frontmostApplication()
        if app is None:
            return False
        return (app.localizedName() or "").lower() in self._skip

    def _focused_window(self):
        app = AppKit.NSWorkspace.sharedWorkspace().frontmostApplication()
        if app is None:
            return None
        ax_app = AXUIElementCreateApplication(app.processIdentifier())
        err, window = AXUIElementCopyAttributeValue(ax_app, "AXFocusedWindow", None)
        if err != 0 or window is None:
            err, windows = AXUIElementCopyAttributeValue(ax_app, "AXWindows", None)
            if err != 0 or not windows:
                return None
            window = windows[0]
        return window

    def _window_position(self, window) -> AppKit.NSPoint | None:
        err, value = AXUIElementCopyAttributeValue(window, "AXPosition", None)
        if err != 0 or value is None:
            return None
        ok, point = AXValueGetValue(value, kAXValueCGPointType, None)
        if not ok:
            return None
        return AppKit.NSPoint(point.x, point.y)

    def _move_window(self, window, point: AppKit.NSPoint) -> bool:
        value = AXValueCreate(kAXValueCGPointType, point)
        return AXUIElementSetAttributeValue(window, "AXPosition", value) == 0
