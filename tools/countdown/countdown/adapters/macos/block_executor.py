"""MacBlockExecutor — the BlockEndExecutor port.

Executes the (bundle_id, action) plan that domain.blockend.plan_block_end
produced: terminate / hide / minimize via NSRunningApplication and AppleScript.
All AppleScript targets apps by bundle identifier — never by display name.
See docs/ports.md and edge-cases.md.
"""

from __future__ import annotations

import subprocess
import time

import AppKit

from countdown import ports
from countdown.domain.blockend import BlockAction

from .applescript_templates import hide_script, minimize_script

_FINDER_BUNDLE_ID = "com.apple.finder"


class MacBlockExecutor:
    """Carries out a block-end plan on macOS."""

    def __init__(self, logger: ports.Logger) -> None:
        self._logger = logger

    def execute(self, plan: list[tuple[str, BlockAction]]) -> dict[str, int]:
        to_quit = [bid for bid, action in plan if action is BlockAction.QUIT]
        to_hide = [bid for bid, action in plan if action is BlockAction.HIDE]
        to_minimize = [bid for bid, action in plan if action is BlockAction.MINIMIZE]

        counts = {"minimize": 0, "hide": 0, "quit": 0}
        failed_quit: list[str] = []

        for bundle_id in to_quit:
            if self._quit_by_bundle_id(bundle_id):
                counts["quit"] += 1
            else:
                failed_quit.append(bundle_id)
                script = hide_script([bundle_id])
                if script and _run_osascript_count(script) > 0:
                    counts["hide"] += 1

        hide_count = _run_hide(to_hide)
        counts["hide"] += hide_count
        counts["minimize"] += _run_minimize(to_minimize)

        if failed_quit:
            self._logger.error(
                f"Could not quit: {', '.join(failed_quit)} "
                "(macOS may block Finder/system apps, or the bundle ID may have changed)."
            )
        return counts

    # -- termination ---------------------------------------------------------

    def _quit_by_bundle_id(self, bundle_id: str) -> bool:
        if bundle_id == _FINDER_BUNDLE_ID:
            # macOS will not quit Finder — hide it instead.
            script = hide_script([bundle_id])
            return bool(script and _run_osascript_count(script) > 0)

        workspace = AppKit.NSWorkspace.sharedWorkspace()
        for app in workspace.runningApplications():
            if (app.bundleIdentifier() or "") != bundle_id:
                continue
            if app.activationPolicy() != AppKit.NSApplicationActivationPolicyRegular:
                continue
            pid = app.processIdentifier()
            if not app.terminate():
                app.forceTerminate()
            for _ in range(30):
                time.sleep(0.1)
                if not any(
                    other.processIdentifier() == pid
                    for other in workspace.runningApplications()
                ):
                    return True
            return False
        return False


def _run_hide(bundle_ids: list[str]) -> int:
    script = hide_script(bundle_ids)
    if not script:
        return 0
    return _run_osascript_count(script)


def _run_minimize(bundle_ids: list[str]) -> int:
    script = minimize_script(bundle_ids)
    if not script:
        return 0
    return _run_osascript_count(script)


def _run_osascript_count(script: str) -> int:
    result = subprocess.run(
        ["osascript", "-e", script], capture_output=True, text=True, check=False
    )
    try:
        return max(0, int(result.stdout.strip()))
    except ValueError:
        return 0
