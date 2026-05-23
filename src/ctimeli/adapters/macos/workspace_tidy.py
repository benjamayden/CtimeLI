"""MacWorkspaceTidy — posts Hide Others + Minimize shortcuts after block-on-end.

Replaces the per-app AppleScript executor. See docs/ports.md and docs/features.md §8.
"""

from __future__ import annotations

import AppKit
import ApplicationServices

from ctimeli import ports
from ctimeli.domain.apps import AppSelector, RunningApp, app_matches_selector

from . import keyboard


class MacWorkspaceTidy:
    """Hide every app except the frontmost, then minimize the frontmost window."""

    def __init__(
        self,
        logger: ports.Logger,
        scheduler: ports.FrameScheduler,
    ) -> None:
        self._logger = logger
        self._scheduler = scheduler
        self._accessibility_warned = False
        self._settings_opened = False

    @staticmethod
    def is_trusted() -> bool:
        return ApplicationServices.AXIsProcessTrusted()

    def ensure_access(self, *, prompt: bool = True) -> bool:
        """Acquire Accessibility permission. Idempotent; may show the system dialog."""
        import sys

        trusted = ApplicationServices.AXIsProcessTrusted()
        if trusted:
            return True
        if prompt:
            from ctimeli.adapters.macos.permissions import activate_for_system_prompt

            activate_for_system_prompt()
            options = {ApplicationServices.kAXTrustedCheckOptionPrompt: True}
            ApplicationServices.AXIsProcessTrustedWithOptions(options)
            if ApplicationServices.AXIsProcessTrusted():
                return True
            if not self._settings_opened:
                self._settings_opened = True
                from ctimeli.adapters.macos.permissions import open_accessibility_settings

                open_accessibility_settings()
                self._logger.info(
                    "System Settings → Accessibility opened. Turn ON Python, then "
                    "./run permissions"
                )
        self._warn_accessibility_denied()
        return False

    def tidy_focused(
        self, *, skip: frozenset[AppSelector], pump: bool = True
    ) -> None:
        if not self.ensure_access(prompt=False):
            return

        keyboard.post_shortcut(keyboard.KEY_H, keyboard.HIDE_OTHERS_FLAGS)
        if pump:
            self._scheduler.pump(0.05)
        self._unhide_skip_apps(skip)

        front = self._frontmost_app()
        if front is not None and not _matches_skip(front, skip):
            keyboard.post_shortcut(keyboard.KEY_M, keyboard.MINIMIZE_FLAGS)

    def _warn_accessibility_denied(self) -> None:
        if not self._accessibility_warned:
            self._logger.warn(
                "Accessibility permission required for workspace tidy "
                "(System Settings → Privacy & Security → Accessibility)."
            )
            self._accessibility_warned = True

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
