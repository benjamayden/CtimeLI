"""MacWorkspaceTidy — posts Hide Others + Minimize shortcuts after block-on-end.

Replaces the per-app AppleScript executor. See docs/ports.md and docs/features.md §8.
"""

from __future__ import annotations

import AppKit
import ApplicationServices

from countdown import ports
from countdown.domain.apps import AppSelector, RunningApp, app_matches_selector

from . import keyboard


class MacWorkspaceTidy:
    """Hide every app except the frontmost, then minimize the frontmost window."""

    def __init__(
        self,
        logger: ports.Logger,
        scheduler: ports.FrameScheduler,
        app_control: ports.AppControl,
    ) -> None:
        self._logger = logger
        self._scheduler = scheduler
        self._app_control = app_control
        self._accessibility_warned = False

    def tidy_focused(self, *, skip: frozenset[AppSelector]) -> None:
        if not ApplicationServices.AXIsProcessTrusted():
            if not self._accessibility_warned:
                self._logger.warn(
                    "Accessibility permission required for workspace tidy "
                    "(System Settings → Privacy & Security → Accessibility)."
                )
                self._accessibility_warned = True
            return

        keyboard.post_shortcut(keyboard.KEY_H, keyboard.HIDE_OTHERS_FLAGS)
        self._scheduler.pump(0.05)
        self._unhide_skip_apps(skip)

        front = self._frontmost_app()
        if front is not None and not _matches_skip(front, skip):
            keyboard.post_shortcut(keyboard.KEY_M, keyboard.MINIMIZE_FLAGS)

    def _unhide_skip_apps(self, skip: frozenset[AppSelector]) -> None:
        if not skip:
            return
        workspace = AppKit.NSWorkspace.sharedWorkspace()
        for app in workspace.runningApplications():
            if app.activationPolicy() != AppKit.NSApplicationActivationPolicyRegular:
                continue
            running = _running_app(app)
            if running is None:
                continue
            if any(app_matches_selector(running, sel) for sel in skip):
                app.unhide()

    def _frontmost_app(self) -> RunningApp | None:
        app = AppKit.NSWorkspace.sharedWorkspace().frontmostApplication()
        if app is None:
            return None
        return _running_app(app)


def _running_app(app: AppKit.NSRunningApplication) -> RunningApp | None:
    display_name = app.localizedName() or ""
    if not display_name:
        return None
    return RunningApp(
        bundle_id=app.bundleIdentifier() or None,
        display_name=display_name,
    )


def _matches_skip(app: RunningApp, skip: frozenset[AppSelector]) -> bool:
    return any(app_matches_selector(app, sel) for sel in skip)
