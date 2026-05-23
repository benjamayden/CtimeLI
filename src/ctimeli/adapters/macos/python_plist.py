"""One-time Python Info.plist patch so EventKit can show the Calendar Allow dialog.

macOS requires NSCalendarsFullAccessUsageDescription on the *running executable's*
bundle. ``python -m ctimeli`` uses org.python.python, whose framework Info.plist
ships without that key — EventKit then returns ``granted=False`` instantly with
no dialog (edge-cases #44).
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

_USAGE_KEY = "NSCalendarsFullAccessUsageDescription"
_USAGE_TEXT = (
    "CtimeLI reads your calendar to auto-start countdown timers before meetings."
)


def python_framework_info_plist() -> Path:
    exe = Path(os.path.realpath(sys.executable))
    # …/Python.framework/Versions/X.Y/bin/python3.Y → …/Resources/Info.plist
    return exe.parent.parent / "Resources" / "Info.plist"


def calendar_usage_description_present() -> bool:
    plist = python_framework_info_plist()
    if not plist.is_file():
        return False
    try:
        subprocess.run(
            ["/usr/libexec/PlistBuddy", "-c", f"Print :{_USAGE_KEY}", str(plist)],
            check=True,
            capture_output=True,
            text=True,
        )
        return True
    except subprocess.CalledProcessError:
        return False


def patch_python_calendar_usage(*, use_sudo: bool = True) -> bool:
    """Add NSCalendarsFullAccessUsageDescription to the Python framework plist."""
    plist = python_framework_info_plist()
    if not plist.is_file():
        return False
    if calendar_usage_description_present():
        return True
    cmd = [
        "/usr/libexec/PlistBuddy",
        "-c",
        f"Add :{_USAGE_KEY} string {_USAGE_TEXT!r}",
        str(plist),
    ]
    if use_sudo:
        cmd = ["sudo", *cmd]
    try:
        subprocess.run(cmd, check=True)
        return calendar_usage_description_present()
    except (subprocess.CalledProcessError, OSError):
        return False
