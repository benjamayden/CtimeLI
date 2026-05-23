"""Composition root — builds adapters, injects them, runs the app.

This is the ONLY module that constructs adapters. It imports the platform; the
domain and app layers never do. See docs/architecture.md.
"""

from __future__ import annotations

import datetime as dt
import os
from pathlib import Path

import AppKit

from ctimeli import ports
from ctimeli.adapters.macos.app_control import MacAppControl
from ctimeli.adapters.macos.watch_menu_bar import MacWatchMenuBar
from ctimeli.adapters.macos.workspace_tidy import MacWorkspaceTidy
from ctimeli.adapters.macos.calendar import EventKitCalendar
from ctimeli.adapters.macos.overlay import MacOverlay
from ctimeli.adapters.macos.runloop import MacScheduler
from ctimeli.adapters.macos.blur import MacScreenBlur
from ctimeli.adapters.macos.stop_overlay import MacStopOverlay
from ctimeli.adapters.macos.url_opener import MacUrlOpener
from ctimeli.adapters.system.clock import SystemClock
from ctimeli.adapters.system.dotenv import DotEnvSource
from ctimeli.adapters.system.logger import StderrLogger
from ctimeli.adapters.system.null_input import NullInputSource
from ctimeli.adapters.system.signals import SigintListener
from ctimeli.adapters.system.wifi import SystemWifi
from ctimeli.app.session_runner import SessionRunner
from ctimeli.app.watch_runner import WatchRunner
from ctimeli.domain.apps import AppSelector, RunningApp, sort_apps_for_manifest
from ctimeli.domain.config import AppConfig
from ctimeli.domain.manifest import format_manifest
from ctimeli.domain.math import format_duration
from ctimeli.domain.session import Session, SessionKind


def request_watch_launch_permissions(
    config: AppConfig, *, watch_argv: list[str] | None = None
) -> bool:
    """Invoke macOS permission dialogs before detaching watch to the background.

    Returns False when the flow was handed off to Terminal.app (caller must exit).
    """
    from ctimeli.adapters.macos.appkit_init import ensure_appkit_initialized
    from ctimeli.adapters.macos.permissions import request_watch_launch_permissions as _request

    ensure_appkit_initialized()
    logger = StderrLogger()
    scheduler = MacScheduler()
    return _request(
        config,
        logger=logger,
        workspace_tidy=MacWorkspaceTidy(logger, scheduler),
        calendar=EventKitCalendar(logger),
        watch_argv=watch_argv or [],
    )


def run_permissions_setup(config: AppConfig, *, perm_argv: list[str] | None = None) -> int:
    """Interactive permission setup (install or ``ctimeli permissions``)."""
    from ctimeli.adapters.macos.permissions import (
        relaunch_permissions_in_terminal,
        run_permissions_setup as _setup,
        should_relaunch_permissions_in_terminal,
    )

    if should_relaunch_permissions_in_terminal():
        relaunch_permissions_in_terminal(perm_argv or [])
        print("", flush=True)
        print(tagged("NEXT", "Opening Terminal.app for setup."), flush=True)
        print(indent("Dialogs do not work in Cursor's terminal."), flush=True)
        print(indent("Come back here when done."), flush=True)
        print("", flush=True)
        return 0

    from ctimeli.adapters.macos.appkit_init import ensure_appkit_initialized

    ensure_appkit_initialized()
    logger = StderrLogger()
    scheduler = MacScheduler()
    _setup(
        config,
        logger=logger,
        workspace_tidy=MacWorkspaceTidy(logger, scheduler),
        calendar=EventKitCalendar(logger),
        wait_for_user=True,
        include_accessibility=True,
    )
    return 0


_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_ENV_PATH = _REPO_ROOT / ".env"
_MANIFEST_PATH = _REPO_ROOT / "apps.manifest"

# Terminal apps — maps TERM_PROGRAM env values to the macOS app display name.
_TERM_PROGRAM_TO_APP = {
    "Apple_Terminal": "Terminal",
    "iTerm.app": "iTerm2",
    "cursor": "Cursor",
    "WarpTerminal": "Warp",
}


def build_config(**cli_overrides: object) -> tuple[AppConfig, list[str]]:
    """Assemble AppConfig: defaults < .env < process env < CLI overrides.

    Returns (config, warnings).
    """
    env = DotEnvSource(_ENV_PATH).values()
    cfg, warnings = AppConfig.from_mapping(env)
    return cfg.merge(**cli_overrides), warnings


def run_one_shot(config: AppConfig, target: dt.datetime) -> int:
    """Run a single countdown to `target`. Returns a process exit code."""
    _init_appkit()
    clock = SystemClock()
    logger = StderrLogger()
    signals = SigintListener()
    signals.install()
    remaining = (target - clock.now()).total_seconds()
    from ctimeli.terminal_ui import ok, tagged

    logger.info(
        tagged(
            "TIME",
            f"Ends {target:%H:%M:%S} ({format_duration(remaining)} left)",
        )
    )
    logger.info(tagged("TIP", "Ctrl+C to quit."))
    app_control = MacAppControl()
    runner = _make_runner(
        config,
        started=clock.now(),
        target=target,
        kind=SessionKind.MANUAL,
        event_start=None,
        event_id=None,
        event_title=None,
        call_url=None,
        room=None,
        clock=clock,
        logger=logger,
        signals=signals,
        app_control=app_control,
        extra_skip=frozenset(),
        url_opener=MacUrlOpener(),
        wifi=SystemWifi(),
    )
    if config.block_on_end:
        runner.workspace_tidy.ensure_access()
    try:
        session = runner.run()
    finally:
        signals.restore()

    from ctimeli.terminal_ui import ok, tagged

    if session.interrupted:
        logger.info(tagged("STOP", "Timer stopped."))
    elif session.blocked:
        logger.info(tagged("STOP", "Time's up."))
    else:
        logger.info(ok(f"Done — {target:%H:%M} reached."))
    return 0


def run_watch(config: AppConfig) -> int:
    """Run watch mode. Returns a process exit code."""
    try:
        return _run_watch_body(config)
    except Exception:
        import traceback
        from ctimeli.adapters.system.detach import watch_log_path

        try:
            path = watch_log_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as log:
                log.write("\n--- watch crash ---\n")
                traceback.print_exc(file=log)
        except OSError:
            traceback.print_exc()
        raise


def _run_watch_body(config: AppConfig) -> int:
    """Run watch mode. Returns a process exit code."""
    import signal

    from ctimeli.adapters.system.watch_lock import WatchInstanceLock

    signal.signal(signal.SIGPIPE, signal.SIG_IGN)
    clock = SystemClock()
    logger = StderrLogger()
    lock = WatchInstanceLock()
    if not lock.try_acquire():
        from ctimeli.terminal_ui import tagged

        logger.info(tagged("WATCH", "Already running — exiting."))
        return 0
    signals = SigintListener()
    input_source = NullInputSource()
    calendar = EventKitCalendar(logger)
    app_control = MacAppControl()
    scheduler = MacScheduler()
    workspace_tidy = MacWorkspaceTidy(logger, scheduler)
    menu_bar = MacWatchMenuBar()
    hosts = _host_terminal_selectors()
    from ctimeli.terminal_ui import tagged

    logger.info(tagged("WATCH", "Starting…"))

    def factory(target, *, kind, event_start, event_id, event_title, call_url, room):
        return _make_runner(
            config,
            started=clock.now(),
            target=target,
            kind=kind,
            event_start=event_start,
            event_id=event_id,
            event_title=event_title,
            call_url=call_url,
            room=room,
            clock=clock,
            logger=logger,
            signals=signals,
            app_control=app_control,
            scheduler=scheduler,
            workspace_tidy=workspace_tidy,
            extra_skip=hosts,
            url_opener=MacUrlOpener(),
            wifi=SystemWifi(),
        )

    from ctimeli.adapters.macos.runloop import run_cocoa_watch_loop

    watch = WatchRunner(
        config=config,
        clock=clock,
        logger=logger,
        input_source=input_source,
        calendar=calendar,
        signals=signals,
        scheduler=scheduler,
        app_control=app_control,
        menu_bar=menu_bar,
        session_factory=factory,
        workspace_tidy=workspace_tidy,
    )
    try:
        return run_cocoa_watch_loop(watch)
    finally:
        lock.release()


def run_apps() -> int:
    """Print a numbered table of running GUI apps and write apps.manifest."""
    _init_appkit()
    ctrl = MacAppControl()
    apps: list[RunningApp] = sort_apps_for_manifest(ctrl.running_apps())
    if not apps:
        print("No regular GUI apps found.")
        return 0

    index_to_bundle: dict[int, str] = {}
    col_w = max(len(a.display_name) for a in apps)
    print()
    for i, app in enumerate(apps, start=1):
        bundle_str = app.bundle_id or "(no bundle ID)"
        print(f"  {i:2}  {app.display_name:<{col_w}}  {bundle_str}")
        if app.bundle_id:
            index_to_bundle[i] = app.bundle_id

    indices_str = ",".join(str(i) for i in sorted(index_to_bundle)[:3])
    print(f"\nExample indices: {indices_str}")

    if index_to_bundle:
        manifest_text = format_manifest(index_to_bundle)
        _MANIFEST_PATH.write_text(manifest_text)
        print(f"Manifest written: {_MANIFEST_PATH}")
    return 0


# -- internals ---------------------------------------------------------------


def _make_runner(
    config: AppConfig,
    *,
    started: dt.datetime,
    target: dt.datetime,
    kind: SessionKind,
    event_start: dt.datetime | None,
    event_id: str | None,
    event_title: str | None,
    call_url: str | None,
    room: str | None,
    clock: ports.Clock,
    logger: ports.Logger,
    signals: ports.SignalListener,
    app_control: ports.AppControl,
    scheduler: ports.FrameScheduler | None = None,
    workspace_tidy: ports.WorkspaceTidy | None = None,
    extra_skip: frozenset[AppSelector],
    url_opener: ports.UrlOpener,
    wifi: ports.WifiSource,
) -> SessionRunner:
    session = Session(
        started=started,
        target=target,
        config=config,
        kind=kind,
        event_start=event_start,
        event_id=event_id,
        event_title=event_title,
        call_url=call_url,
        room=room,
    )
    if scheduler is None:
        scheduler = MacScheduler()
    if workspace_tidy is None:
        workspace_tidy = MacWorkspaceTidy(logger, scheduler)
    return SessionRunner(
        session,
        clock=clock,
        logger=logger,
        scheduler=scheduler,
        overlay=MacOverlay(config, logger),
        stop_overlay=MacStopOverlay(),
        blur=MacScreenBlur(),
        app_control=app_control,
        workspace_tidy=workspace_tidy,
        signals=signals,
        extra_skip=extra_skip,
        url_opener=url_opener,
        wifi=wifi,
    )


def _host_terminal_selectors() -> frozenset[AppSelector]:
    """Selectors for only the *current* launching terminal — block-end extra_skip.

    Only skips the terminal we were actually launched from, so other open
    terminals (e.g. Terminal.app when launched from Cursor) are still tidied.
    """
    detected: set[str] = set()
    term = os.environ.get("TERM_PROGRAM", "").strip()
    if term:
        detected.add(term)
        mapped = _TERM_PROGRAM_TO_APP.get(term)
        if mapped:
            detected.add(mapped)
    return frozenset(
        AppSelector(kind="display_name", value=name)
        for name in detected
    )


def _init_appkit() -> None:
    from ctimeli.adapters.macos.appkit_init import ensure_appkit_initialized

    ensure_appkit_initialized()
