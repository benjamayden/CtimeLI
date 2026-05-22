"""MacBlockExecutor — the BlockEndExecutor port.

Executes the (app, action) plan that domain.blockend.plan_block_end produced:
terminate / hide / minimize via NSRunningApplication and AppleScript. The plan
is already filtered of skipped apps. See docs/ports.md.
"""

from __future__ import annotations

import subprocess
import time

import AppKit

from countdown import ports
from countdown.domain.blockend import BlockAction, expand_aliases


class MacBlockExecutor:
    """Carries out a block-end plan on macOS."""

    def __init__(self, logger: ports.Logger) -> None:
        self._logger = logger

    def execute(self, plan: list[tuple[str, BlockAction]]) -> dict[str, int]:
        to_quit = [name for name, action in plan if action is BlockAction.QUIT]
        to_hide = [name for name, action in plan if action is BlockAction.HIDE]
        to_minimize = [name for name, action in plan if action is BlockAction.MINIMIZE]

        counts = {"minimize": 0, "hide": 0, "quit": 0}
        failed_quit: list[str] = []

        for name in to_quit:
            if self._quit_application(name):
                counts["quit"] += 1
            else:
                failed_quit.append(name)
                if self._hide_processes([name]) > 0:
                    counts["hide"] += 1

        counts["hide"] += self._hide_processes(to_hide)
        counts["minimize"] += self._minimize_processes(to_minimize)

        if failed_quit:
            self._logger.error(
                f"Could not quit: {', '.join(failed_quit)} "
                "(macOS may block Finder/system apps, or the name may differ)."
            )
        return counts

    # -- termination ---------------------------------------------------------

    def _quit_application(self, process_name: str) -> bool:
        if process_name == "Finder":
            # macOS will not quit Finder — hide it instead.
            return self._hide_processes(["Finder"]) > 0

        targets = expand_aliases([process_name])
        target_lowers = {name.lower() for name in targets}
        workspace = AppKit.NSWorkspace.sharedWorkspace()
        for app in workspace.runningApplications():
            name = app.localizedName() or ""
            if name not in targets and name.lower() not in target_lowers:
                continue
            if app.activationPolicy() != AppKit.NSApplicationActivationPolicyRegular:
                continue
            pid = app.processIdentifier()
            if not app.terminate():
                app.forceTerminate()
            for _ in range(10):
                time.sleep(0.1)
                if not any(
                    other.processIdentifier() == pid
                    for other in workspace.runningApplications()
                ):
                    return True
            return False
        return False

    # -- AppleScript hide / minimize ----------------------------------------

    def _hide_processes(self, processes: list[str]) -> int:
        if not processes:
            return 0
        script = f"""
set hideCount to 0
tell application "System Events"
    repeat with procName in {_name_list(processes)}
        try
            set visible of process procName to false
            set hideCount to hideCount + 1
        end try
    end repeat
end tell
return hideCount
"""
        return _run_osascript_count(script)

    def _minimize_processes(self, processes: list[str]) -> int:
        if not processes:
            return 0
        script = f"""
set minCount to 0
tell application "System Events"
    repeat with procName in {_name_list(processes)}
        try
            tell process procName
                set windowCount to count of windows
                repeat with i from windowCount to 1 by -1
                    try
                        set value of attribute "AXMinimized" of window i to true
                        set minCount to minCount + 1
                    end try
                end repeat
            end tell
        end try
    end repeat
end tell
return minCount
"""
        return _run_osascript_count(script)


def _name_list(names: list[str]) -> str:
    """Render an AppleScript list literal of process names."""
    if not names:
        return "{}"
    return "{" + ", ".join(f'"{name}"' for name in sorted(set(names))) + "}"


def _run_osascript_count(script: str) -> int:
    result = subprocess.run(
        ["osascript", "-e", script], capture_output=True, text=True, check=False
    )
    try:
        return max(0, int(result.stdout.strip()))
    except ValueError:
        return 0
