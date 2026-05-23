"""Composition root — builds adapters, injects them, runs the app.

This is the ONLY module that constructs adapters. It imports the platform; the
domain and app layers never do. See docs/architecture.md.
"""

from __future__ import annotations

import datetime as dt
import os
from pathlib import Path

import AppKit

from countdown import ports
from countdown.adapters.macos.app_control import MacAppControl
from countdown.adapters.macos.workspace_tidy import MacWorkspaceTidy
from countdown.adapters.macos.calendar import EventKitCalendar
from countdown.adapters.macos.overlay import MacOverlay
from countdown.adapters.macos.runloop import MacScheduler
from countdown.adapters.macos.blur import MacScreenBlur
from countdown.adapters.macos.stop_overlay import MacStopOverlay
from countdown.adapters.macos.url_opener import MacUrlOpener
from countdown.adapters.system.clock import SystemClock
from countdown.adapters.system.dotenv import DotEnvSource
from countdown.adapters.system.logger import StderrLogger
from countdown.adapters.system.signals import SigintListener
from countdown.adapters.system.stdin_source import StdinSource
from countdown.adapters.system.wifi import SystemWifi
from countdown.app.session_runner import SessionRunner
from countdown.app.watch_runner import WatchRunner
from countdown.domain.apps import AppSelector, RunningApp, sort_apps_for_manifest
from countdown.domain.config import AppConfig
from countdown.domain.manifest import format_manifest
from countdown.domain.math import format_duration
from countdown.domain.session import Session, SessionKind

_ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
_MANIFEST_PATH = Path(__file__).resolve().parent.parent / "apps.manifest"

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
    logger.info(
        f"Countdown → {target:%H:%M:%S} ({format_duration(remaining)} remaining)"
    )
    logger.info("Ctrl+C to quit.")
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
    try:
        session = runner.run()
    finally:
        signals.restore()

    if session.interrupted:
        logger.info("Stopped.")
    elif session.blocked:
        logger.info("It's time to stop.")
    else:
        logger.info(f"Done — {target:%H:%M} reached.")
    return 0


def run_watch(config: AppConfig) -> int:
    """Run watch mode. Returns a process exit code."""
    _init_appkit()
    clock = SystemClock()
    logger = StderrLogger()
    signals = SigintListener()
    input_source = StdinSource()
    calendar = EventKitCalendar(logger)
    app_control = MacAppControl()
    scheduler = MacScheduler()
    hosts = _host_terminal_selectors()

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
            extra_skip=hosts,
            url_opener=MacUrlOpener(),
            wifi=SystemWifi(),
        )

    watch = WatchRunner(
        config=config,
        clock=clock,
        logger=logger,
        input_source=input_source,
        calendar=calendar,
        signals=signals,
        scheduler=scheduler,
        app_control=app_control,
        session_factory=factory,
    )
    return watch.run()


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
    return SessionRunner(
        session,
        clock=clock,
        logger=logger,
        scheduler=scheduler,
        overlay=MacOverlay(config, logger),
        stop_overlay=MacStopOverlay(),
        blur=MacScreenBlur(),
        app_control=app_control,
        workspace_tidy=MacWorkspaceTidy(logger, scheduler),
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
    AppKit.NSApplication.sharedApplication()
