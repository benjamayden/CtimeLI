"""Composition root — builds adapters, injects them, runs the app.

This is the ONLY module that constructs adapters. It imports the platform; the
domain and app layers never do. See docs/architecture.md.
"""

from __future__ import annotations

import datetime as dt
import os
from pathlib import Path

import AppKit

from countdown.adapters.macos.app_control import MacAppControl
from countdown.adapters.macos.block_executor import MacBlockExecutor
from countdown.adapters.macos.calendar import EventKitCalendar
from countdown.adapters.macos.overlay import MacOverlay
from countdown.adapters.macos.runloop import MacScheduler
from countdown.adapters.macos.shaker import MacShaker
from countdown.adapters.macos.stop_overlay import MacStopOverlay
from countdown.adapters.system.clock import SystemClock
from countdown.adapters.system.dotenv import DotEnvSource
from countdown.adapters.system.logger import StderrLogger
from countdown.adapters.system.signals import SigintListener
from countdown.adapters.system.stdin_source import StdinSource
from countdown.app.session_runner import SessionRunner
from countdown.app.watch_runner import WatchRunner
from countdown.domain.apps import AppSelector, RunningApp, sort_apps_for_manifest
from countdown.domain.config import AppConfig
from countdown.domain.manifest import format_manifest, parse_manifest
from countdown.domain.math import format_duration
from countdown.domain.session import Session, SessionKind

_ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
_MANIFEST_PATH = Path(__file__).resolve().parent.parent / "apps.manifest"

# System processes the wiggle never targets (they can't be meaningfully moved).
_NEVER_WIGGLE = frozenset(
    {"SystemUIServer", "WindowManager", "Dock", "loginwindow", "Python", "python"}
)
# Terminal apps — used for block-end extra_skip only (not for shake skip).
_HOST_TERMINALS = frozenset({"Terminal", "iTerm2", "iTerm", "Warp", "Cursor"})
# Maps TERM_PROGRAM env values to the macOS app display name.
_TERM_PROGRAM_TO_APP = {
    "Apple_Terminal": "Terminal",
    "iTerm.app": "iTerm2",
    "cursor": "Cursor",
    "WarpTerminal": "Warp",
}


def build_config(**cli_overrides: object) -> tuple[AppConfig, list[str]]:
    """Assemble AppConfig: defaults < .env < process env < CLI overrides.

    Returns (config, warnings) where warnings are stale manifest index messages.
    """
    env = DotEnvSource(_ENV_PATH).values()
    manifest = _load_manifest()
    cfg, warnings = AppConfig.from_mapping(env, manifest=manifest)
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
    runner = _make_runner(
        config,
        started=clock.now(),
        target=target,
        kind=SessionKind.MANUAL,
        event_start=None,
        event_id=None,
        event_title=None,
        clock=clock,
        logger=logger,
        signals=signals,
        extra_skip=frozenset(),
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
    hosts = _host_terminal_selectors()

    def factory(target, *, kind, event_start, event_id, event_title):
        return _make_runner(
            config,
            started=clock.now(),
            target=target,
            kind=kind,
            event_start=event_start,
            event_id=event_id,
            event_title=event_title,
            clock=clock,
            logger=logger,
            signals=signals,
            extra_skip=hosts,
        )

    watch = WatchRunner(
        config=config,
        clock=clock,
        logger=logger,
        input_source=input_source,
        calendar=calendar,
        signals=signals,
        scheduler=MacScheduler(),
        app_control=MacAppControl(),
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
    print(f"\nCopy into .env:  BLOCK_END_QUIT={indices_str}")

    if index_to_bundle:
        manifest_text = format_manifest(index_to_bundle)
        _MANIFEST_PATH.write_text(manifest_text)
        print(f"Manifest written: {_MANIFEST_PATH}")
    return 0


# -- internals ---------------------------------------------------------------


def _load_manifest() -> dict[int, str]:
    if not _MANIFEST_PATH.exists():
        return {}
    try:
        return parse_manifest(_MANIFEST_PATH.read_text())
    except OSError:
        return {}


def _make_runner(
    config: AppConfig,
    *,
    started: dt.datetime,
    target: dt.datetime,
    kind: SessionKind,
    event_start: dt.datetime | None,
    event_id: str | None,
    event_title: str | None,
    clock: SystemClock,
    logger: StderrLogger,
    signals: SigintListener,
    extra_skip: frozenset[AppSelector],
) -> SessionRunner:
    session = Session(
        started=started,
        target=target,
        config=config,
        kind=kind,
        event_start=event_start,
        event_id=event_id,
        event_title=event_title,
    )
    return SessionRunner(
        session,
        clock=clock,
        logger=logger,
        scheduler=MacScheduler(),
        overlay=MacOverlay(config, logger),
        stop_overlay=MacStopOverlay(),
        shaker=MacShaker(logger, _NEVER_WIGGLE),
        app_control=MacAppControl(),
        block_executor=MacBlockExecutor(logger),
        signals=signals,
        extra_skip=extra_skip,
    )


def _host_terminal_names() -> frozenset[str]:
    """All known terminal names — used for wiggle skip (don't shake any terminal)."""
    names = set(_HOST_TERMINALS)
    term = os.environ.get("TERM_PROGRAM", "").strip()
    if term:
        names.add(term)
        mapped = _TERM_PROGRAM_TO_APP.get(term)
        if mapped:
            names.add(mapped)
    return frozenset(names)


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
