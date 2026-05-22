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
from countdown.domain.config import AppConfig
from countdown.domain.math import format_duration
from countdown.domain.session import Session, SessionKind

_ENV_PATH = Path(__file__).resolve().parent.parent / ".env"

# Apps the wiggle never targets (system UI + the Python process itself).
_NEVER_WIGGLE = frozenset(
    {"SystemUIServer", "WindowManager", "Dock", "loginwindow", "Python", "python"}
)
# Terminal apps to leave alone — wiggle skips them, watch block-end skips them.
_HOST_TERMINALS = frozenset({"Terminal", "iTerm2", "iTerm", "Warp", "Cursor"})
_TERM_PROGRAM_TO_APP = {"Apple_Terminal": "Terminal", "iTerm.app": "iTerm2"}


def build_config(**cli_overrides: object) -> AppConfig:
    """Assemble AppConfig: defaults < .env < process env < CLI overrides."""
    env = DotEnvSource(_ENV_PATH).values()
    return AppConfig.from_mapping(env).merge(**cli_overrides)


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
    hosts = _host_terminals()

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
    clock: SystemClock,
    logger: StderrLogger,
    signals: SigintListener,
    extra_skip: frozenset[str],
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
        shaker=MacShaker(logger, _NEVER_WIGGLE | _host_terminals()),
        app_control=MacAppControl(),
        block_executor=MacBlockExecutor(logger),
        signals=signals,
        extra_skip=extra_skip,
    )


def _host_terminals() -> frozenset[str]:
    names = set(_HOST_TERMINALS)
    term = os.environ.get("TERM_PROGRAM", "").strip()
    if term:
        names.add(term)
        mapped = _TERM_PROGRAM_TO_APP.get(term)
        if mapped:
            names.add(mapped)
    return frozenset(names)


def _init_appkit() -> None:
    AppKit.NSApplication.sharedApplication()
