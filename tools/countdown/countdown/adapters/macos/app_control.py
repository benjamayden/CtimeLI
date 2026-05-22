"""MacAppControl — the AppControl port via NSWorkspace / NSApp.

Query and steer running applications: focus, listing, activation policy.
See docs/ports.md and edge-cases.md "Unverified surface".
"""

from __future__ import annotations

import subprocess

import AppKit

from countdown import ports

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
            return None  # never "restore focus" to ourselves
        return int(app.processIdentifier())

    def app_name_for_pid(self, pid: int) -> str | None:
        for app in AppKit.NSWorkspace.sharedWorkspace().runningApplications():
            if app.processIdentifier() == pid:
                return app.localizedName()
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

    def running_app_names(self) -> list[str]:
        workspace = AppKit.NSWorkspace.sharedWorkspace()
        names: list[str] = []
        seen: set[str] = set()
        for app in workspace.runningApplications():
            if app.activationPolicy() != AppKit.NSApplicationActivationPolicyRegular:
                continue
            name = app.localizedName() or ""
            if name and name not in seen:
                seen.add(name)
                names.append(name)
        return names

    def foreground_app_names(self) -> list[str]:
        result = subprocess.run(
            [
                "osascript",
                "-e",
                'tell application "System Events" to get name of every process '
                "whose background only is false",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            return []
        raw = result.stdout.strip()
        if not raw:
            return []
        return [name.strip() for name in raw.split(", ") if name.strip()]

    def set_activation_policy(self, policy: ports.ActivationPolicy) -> None:
        AppKit.NSApp.setActivationPolicy_(_POLICY_MAP[policy])
        if policy is ports.ActivationPolicy.PROHIBITED:
            AppKit.NSApp.hide_(None)
