"""macOS privacy prompts — invoke system dialogs before background detach.

Accessibility and Calendar prompts must run in the foreground launcher process;
a detached watch child often cannot show them (edge-cases #43).

The watch child runs as ``sys.executable`` (``.venv/bin/python``), which macOS
lists as **Python** in Accessibility — separate from Terminal.app.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import AppKit
import ApplicationServices

from ctimeli import ports
from ctimeli.adapters.system.runtime import runtime_python
from ctimeli.terminal_ui import (
    emit_info,
    emit_warn,
    indent,
    ok,
    prompt,
    section,
    skip,
    step,
    tagged,
    warn,
)
from ctimeli.domain.config import AppConfig

_ACCESSIBILITY_SETTINGS = (
    "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility"
)
_CALENDAR_SETTINGS = (
    "x-apple.systempreferences:com.apple.preference.security?Privacy_Calendars"
)
_CALENDAR_USAGE_KEY = "NSCalendarsFullAccessUsageDescription"


def setup_marker_path() -> Path:
    override = os.environ.get("CTIMELI_PERMISSIONS_MARKER")
    if override:
        return Path(override)
    return Path.home() / ".cache" / "ctimeli" / "permissions.setup"


def permissions_setup_needed() -> bool:
    return not setup_marker_path().exists()


def mark_permissions_setup_done() -> None:
    path = setup_marker_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch()


def accessibility_client_label() -> str:
    """Human-facing label for the process macOS adds to Accessibility."""
    return runtime_python()


def accessibility_granted() -> bool:
    return ApplicationServices.AXIsProcessTrusted()


def calendar_granted(calendar: ports.CalendarSource) -> bool:
    """True when calendar read access is already granted (never prompts)."""
    check = getattr(calendar, "access_granted", None)
    if callable(check):
        return bool(check())
    return calendar.ensure_access()


def open_privacy_settings(url: str) -> None:
    """Open a System Settings privacy pane (Accessibility, Calendars, …)."""
    AppKit.NSWorkspace.sharedWorkspace().openURL_(AppKit.NSURL.URLWithString_(url))


def open_accessibility_settings() -> None:
    open_privacy_settings(_ACCESSIBILITY_SETTINGS)


def open_calendar_settings() -> None:
    open_privacy_settings(_CALENDAR_SETTINGS)


def activate_for_system_prompt() -> None:
    """Prepare AppKit so system permission sheets can run."""
    from ctimeli.adapters.macos.appkit_init import ensure_appkit_initialized
    from ctimeli.adapters.macos.runloop import pump_run_loop

    ensure_appkit_initialized()
    pump_run_loop(0.05)


def _embedded_terminal() -> bool:
    return os.environ.get("TERM_PROGRAM", "").lower() in {
        "cursor",
        "vscode",
        "code",
    }


def should_relaunch_permissions_in_terminal() -> bool:
    if os.environ.get("CTIMELI_PERMISSIONS_IN_TERMINAL") == "1":
        return False
    if "pytest" in sys.modules:
        return False
    return _embedded_terminal()


def relaunch_permissions_in_terminal(extra_argv: list[str]) -> None:
    """Open Terminal.app — macOS dialogs abort from Cursor's terminal (#45)."""
    import shlex

    args = " ".join(shlex.quote(a) for a in extra_argv)
    cmd_line = f"./run permissions {args}".strip()
    _write_terminal_launcher("ctimeli-permissions.command", cmd_line)


def relaunch_watch_in_terminal(watch_argv: list[str]) -> None:
    """Open Terminal.app for first-time watch permissions + launch."""
    import shlex

    args = " ".join(shlex.quote(a) for a in watch_argv)
    cmd_line = f"./run watch {args}".strip()
    _write_terminal_launcher("ctimeli-watch.command", cmd_line)


def _write_terminal_launcher(filename: str, cmd_line: str) -> None:
    import shlex
    import subprocess
    import tempfile

    script = (
        "#!/bin/bash\n"
        f"cd {shlex.quote(os.getcwd())}\n"
        "export CTIMELI_PERMISSIONS_IN_TERMINAL=1\n"
        f"exec {cmd_line}\n"
    )
    path = Path(tempfile.gettempdir()) / filename
    path.write_text(script, encoding="utf-8")
    path.chmod(0o755)
    subprocess.run(["open", "-a", "Terminal", str(path)], check=False)


def ensure_calendar_dialog_ready(logger: ports.Logger) -> bool:
    """Return False when Python's Info.plist blocks the Calendar Allow dialog."""
    from ctimeli.adapters.macos.python_plist import (
        calendar_usage_description_present,
    )

    if calendar_usage_description_present():
        return True
    emit_warn(
        logger,
        warn("Calendar dialog blocked."),
        indent("Run ./install.sh once (needs sudo)."),
    )
    return False


def _print_guide_header(logger: ports.Logger) -> None:
    emit_info(
        logger,
        *section("permissions (optional)"),
        tagged("NOTE", "Timers work without these."),
        indent("Accessibility — tidy windows at block-end"),
        indent("Calendar — auto-start before meetings"),
        "",
        tagged("TIP", "Use Terminal.app if no popup appears."),
        indent("Cursor's terminal cannot show macOS dialogs."),
    )


def _print_summary(
    logger: ports.Logger,
    *,
    need_accessibility: bool,
    accessibility_ok: bool | None,
    need_calendar: bool,
    calendar_ok: bool | None,
) -> None:
    rows: list[str] = []
    if need_accessibility and accessibility_ok is not None:
        mark = "OK" if accessibility_ok else "SKIP"
        rows.append(f"  Accessibility   {mark}")
    if need_calendar and calendar_ok is not None:
        mark = "OK" if calendar_ok else "SKIP"
        rows.append(f"  Calendar        {mark}")

    all_ok = (
        (not need_accessibility or accessibility_ok)
        and (not need_calendar or calendar_ok)
    )

    lines = [*section("summary"), *rows, ""]
    if all_ok:
        lines.append(ok("All set."))
    else:
        lines.extend(
            [
                tagged("NOTE", "Timers still work without these."),
                prompt("Run ./run permissions to retry."),
            ]
        )
    lines.append("")
    emit_info(logger, *lines)


def _wait_for_enter(logger: ports.Logger, message: str) -> bool:
    if not sys.stdin.isatty():
        return False
    emit_info(logger, "", prompt(message))
    try:
        input()
    except EOFError:
        return False
    return True


def run_permissions_setup(
    config: AppConfig,
    *,
    logger: ports.Logger,
    workspace_tidy: ports.WorkspaceTidy,
    calendar: ports.CalendarSource,
    wait_for_user: bool = True,
    include_accessibility: bool | None = None,
    show_guide: bool = True,
) -> bool:
    """Prompt for optional permissions. Returns True when required access is granted."""
    need_accessibility = (
        config.block_on_end if include_accessibility is None else include_accessibility
    )
    need_calendar = config.calendar_enabled

    if show_guide and wait_for_user:
        _print_guide_header(logger)

    ok_result = True
    accessibility_ok: bool | None = None
    calendar_ok: bool | None = None

    if need_accessibility:
        emit_info(
            logger,
            *section("accessibility"),
            tagged("FOR", "Block-end window tidy."),
            "",
            step(1, "Click Allow in the popup."),
            step(2, 'Turn ON "Python" in System Settings.'),
            indent(accessibility_client_label()),
        )
        activate_for_system_prompt()
        accessibility_ok = workspace_tidy.ensure_access()
        if not accessibility_ok and wait_for_user and _wait_for_enter(
            logger, "Press Enter when the toggle is ON."
        ):
            accessibility_ok = workspace_tidy.ensure_access(prompt=False)
        if not accessibility_ok:
            ok_result = False
            if wait_for_user:
                emit_warn(logger, skip("Accessibility off — block-end tidy disabled."))
        else:
            emit_info(logger, "", ok("Accessibility enabled."))

    if need_calendar:
        emit_info(
            logger,
            *section("calendar"),
            tagged("FOR", "Watch auto-start before meetings."),
        )
        if not ensure_calendar_dialog_ready(logger):
            calendar_ok = False
            ok_result = False
        else:
            emit_info(
                logger,
                "",
                step(1, 'Click Allow on "Python would like calendars".'),
                indent("No + button in Settings — use the popup."),
            )
            activate_for_system_prompt()
            calendar_ok = calendar.ensure_access()
            if not calendar_ok and wait_for_user and _wait_for_enter(
                logger, "Press Enter after Allow (or to skip)."
            ):
                recheck = getattr(calendar, "recheck_access", None)
                calendar_ok = (
                    recheck() if callable(recheck) else calendar.ensure_access()
                )
            if calendar_ok:
                emit_info(logger, "", ok("Calendar enabled."))
            else:
                ok_result = False
                if wait_for_user:
                    emit_warn(logger, skip("Calendar off — auto-start disabled."))

    if show_guide and wait_for_user:
        _print_summary(
            logger,
            need_accessibility=need_accessibility,
            accessibility_ok=accessibility_ok,
            need_calendar=need_calendar,
            calendar_ok=calendar_ok,
        )

    if wait_for_user:
        all_ok = (
            (not need_accessibility or accessibility_ok)
            and (not need_calendar or calendar_ok)
        )
        if all_ok:
            mark_permissions_setup_done()

    return ok_result


def request_watch_launch_permissions(
    config: AppConfig,
    *,
    logger: ports.Logger,
    workspace_tidy: ports.WorkspaceTidy,
    calendar: ports.CalendarSource,
    watch_argv: list[str] | None = None,
) -> bool:
    """Prompt for optional permissions while the watch launcher is still foreground.

    Returns False when the flow was handed off to Terminal.app.
    """
    need_ax = config.block_on_end
    ax_ok = not need_ax or accessibility_granted()
    cal_ok = not config.calendar_enabled or calendar_granted(calendar)

    if not permissions_setup_needed() and ax_ok and cal_ok:
        return True

    if should_relaunch_permissions_in_terminal():
        relaunch_watch_in_terminal(watch_argv or [])
        return False

    wait = (
        permissions_setup_needed()
        or (need_ax and not ax_ok)
        or (config.calendar_enabled and not cal_ok)
    )
    run_permissions_setup(
        config,
        logger=logger,
        workspace_tidy=workspace_tidy,
        calendar=calendar,
        wait_for_user=wait,
        show_guide=wait,
    )
    return True
