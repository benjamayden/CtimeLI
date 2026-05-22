"""MacAppControl — the AppControl port via NSWorkspace / NSApp.

Query and steer running applications: focus, listing, activation policy.
See docs/ports.md and edge-cases.md "Unverified surface".
"""

from __future__ import annotations

import subprocess

import AppKit
import Quartz

from countdown import ports
from countdown.domain.apps import RunningApp

_OWN_PROCESS_NAMES = {"python", "org.python.python"}

_POLICY_MAP = {
    ports.ActivationPolicy.ACCESSORY: AppKit.NSApplicationActivationPolicyAccessory,
    ports.ActivationPolicy.PROHIBITED: AppKit.NSApplicationActivationPolicyProhibited,
    ports.ActivationPolicy.REGULAR: AppKit.NSApplicationActivationPolicyRegular,
}


class MacAppControl:
    """Application focus, listing and activation policy on macOS."""

    def frontmost_pid(self) -> int | None:
        app = AppKit.NSWorkspace.sharedWorkspace().frontmostApplication()
        if app is None:
            return None
        name = (app.localizedName() or "").lower()
        if name in _OWN_PROCESS_NAMES:
            return None
        return int(app.processIdentifier())

    def app_for_pid(self, pid: int) -> RunningApp | None:
        for app in AppKit.NSWorkspace.sharedWorkspace().runningApplications():
            if app.processIdentifier() == pid:
                bundle_id = app.bundleIdentifier() or None
                display_name = app.localizedName() or ""
                return RunningApp(bundle_id=bundle_id, display_name=display_name)
        return None

    def activate_pid(self, pid: int) -> bool:
        for app in AppKit.NSWorkspace.sharedWorkspace().runningApplications():
            if app.processIdentifier() == pid:
                return bool(
                    app.activateWithOptions_(
                        AppKit.NSApplicationActivateIgnoringOtherApps
                        | AppKit.NSApplicationActivateAllWindows
                    )
                )
        return False

    def activate_finder(self) -> None:
        subprocess.run(
            ["osascript", "-e", 'tell application "Finder" to activate'],
            capture_output=True,
            check=False,
        )

    def running_apps(self) -> list[RunningApp]:
        workspace = AppKit.NSWorkspace.sharedWorkspace()
        apps: list[RunningApp] = []
        seen_bundle_ids: set[str] = set()
        seen_names: set[str] = set()
        for app in workspace.runningApplications():
            if app.activationPolicy() != AppKit.NSApplicationActivationPolicyRegular:
                continue
            bundle_id: str | None = app.bundleIdentifier() or None
            display_name = app.localizedName() or ""
            if not display_name:
                continue
            # Deduplicate by bundle ID first, then by name.
            key = bundle_id if bundle_id else display_name
            if bundle_id and bundle_id in seen_bundle_ids:
                continue
            if display_name in seen_names:
                continue
            if bundle_id:
                seen_bundle_ids.add(bundle_id)
            seen_names.add(display_name)
            apps.append(RunningApp(bundle_id=bundle_id, display_name=display_name))
        return apps

    def foreground_apps(self) -> list[RunningApp]:
        """Apps that have windows currently visible on screen (via CGWindowList).

        Uses the window server directly — no AppleScript, no Automation permission.
        Minimized windows are excluded because they are in the Dock, not on screen.
        kCGWindowListExcludeDesktopElements drops the Finder desktop/wallpaper
        layer so Finder only appears when it has an actual folder window open.
        """
        window_list = Quartz.CGWindowListCopyWindowInfo(
            Quartz.kCGWindowListOptionOnScreenOnly
            | Quartz.kCGWindowListExcludeDesktopElements,
            Quartz.kCGNullWindowID,
        )
        pids_with_windows: set[int] = set()
        if window_list:
            for win in window_list:
                pid = win.get("kCGWindowOwnerPID")
                if pid is not None:
                    pids_with_windows.add(int(pid))

        workspace = AppKit.NSWorkspace.sharedWorkspace()
        apps: list[RunningApp] = []
        seen_pids: set[int] = set()
        for app in workspace.runningApplications():
            pid = int(app.processIdentifier())
            if pid not in pids_with_windows or pid in seen_pids:
                continue
            if app.activationPolicy() != AppKit.NSApplicationActivationPolicyRegular:
                continue
            seen_pids.add(pid)
            bundle_id = app.bundleIdentifier() or None
            display_name = app.localizedName() or ""
            if display_name:
                apps.append(RunningApp(bundle_id=bundle_id, display_name=display_name, is_foreground=True))
        return apps

    def set_activation_policy(self, policy: ports.ActivationPolicy) -> None:
        AppKit.NSApp.setActivationPolicy_(_POLICY_MAP[policy])
        if policy is ports.ActivationPolicy.PROHIBITED:
            AppKit.NSApp.hide_(None)
