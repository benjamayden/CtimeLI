"""WatchRunner — the long-lived watch-mode loop.

Listens for quick-add input and calendar events; spawns and retargets a
SessionRunner. Like SessionRunner it is written against ports and a session
factory, so it is testable with fakes.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Protocol

from countdown import ports
from countdown.domain.calendar import CalendarEvent, calendar_block_target, hard_stop_target
from countdown.domain.config import AppConfig
from countdown.domain.math import format_duration
from countdown.domain.session import FRAME_INTERVAL, SessionKind
from countdown.domain.timespec import parse_quick_input

from .session_runner import SessionRunner

# Below this difference a calendar target is "the same" — do not retarget.
_RETARGET_EPSILON_SECONDS = 1.0


@dataclass(frozen=True)
class _WatchCandidate:
    target: dt.datetime
    kind: SessionKind
    event_start: dt.datetime | None = None
    event_id: str | None = None
    event_title: str | None = None
    call_url: str | None = None
    room: str | None = None


class SessionFactory(Protocol):
    """Builds a fully-wired SessionRunner for a target time."""

    def __call__(
        self,
        target: dt.datetime,
        *,
        kind: SessionKind,
        event_start: dt.datetime | None,
        event_id: str | None,
        event_title: str | None,
        call_url: str | None,
        room: str | None,
    ) -> SessionRunner: ...


class WatchRunner:
    """Drives watch mode: stdin quick-add + calendar auto-start / snap."""

    def __init__(
        self,
        *,
        config: AppConfig,
        clock: ports.Clock,
        logger: ports.Logger,
        input_source: ports.InputSource,
        calendar: ports.CalendarSource,
        signals: ports.SignalListener,
        scheduler: ports.FrameScheduler,
        app_control: ports.AppControl,
        session_factory: SessionFactory,
    ) -> None:
        self.config = config
        self.clock = clock
        self.logger = logger
        self.input_source = input_source
        self.calendar = calendar
        self.signals = signals
        self.scheduler = scheduler
        self.app_control = app_control
        self.session_factory = session_factory
        self._current: SessionRunner | None = None
        self._quit = False
        self._last_cal_poll = 0.0
        # Calendar event ids already fired — prevents re-trigger (edge-cases #29).
        self._finished_events: set[str] = set()

    def run(self) -> int:
        """Run the watch loop until the user quits. Returns an exit code."""
        self.signals.install()
        self._go_idle()
        try:
            self._announce()
            while not self._quit:
                if self.signals.interrupted():
                    break
                self._poll_input()
                self._poll_calendar()
                self._pump_current()
        finally:
            self._shutdown()
        return 0

    # -- startup / shutdown --------------------------------------------------

    def _announce(self) -> None:
        if self.config.calendar_enabled:
            self.calendar.ensure_access()
        if not self._start_from_nearest():
            if self.config.calendar_enabled:
                self.logger.info("Calendar: no accepted event in the next window.")
        self.logger.info("Watcher ready — enter 15, 14:00, or q to quit.")
        if self.config.block_on_end:
            self.logger.info("Block on end: dismiss the stop overlay to tidy windows.")

    def _shutdown(self) -> None:
        if self._current is not None:
            self._current.session.interrupt()
            while self._current.pump():
                pass
            self._current = None
        self.input_source.close()
        self.signals.restore()
        self.scheduler.stop()

    def _go_idle(self) -> None:
        self.app_control.set_activation_policy(ports.ActivationPolicy.PROHIBITED)

    # -- per-loop steps ------------------------------------------------------

    def _pump_current(self) -> None:
        if self._current is None:
            self.scheduler.pump(FRAME_INTERVAL)
            return
        if self._current.pump():
            return
        session = self._current.session
        if (
            session.kind is SessionKind.CALENDAR
            and session.event_id
            and session.blocked
            and not session.interrupted
        ):
            self._finished_events.add(session.event_id)
        self._current = None
        self._go_idle()

    def _poll_input(self) -> None:
        if self.input_source.closed():
            self._quit = True
            return
        for line in self.input_source.poll_lines():
            self._handle_line(line)

    def _handle_line(self, line: str) -> None:
        text = line.strip()
        if not text:
            return
        if text.lower() in {"q", "quit", "exit"}:
            self._quit = True
            return
        try:
            target = parse_quick_input(text, self.clock.now())
        except ValueError as exc:
            self.logger.error(str(exc))
            return
        if (target - self.clock.now()).total_seconds() <= 0:
            self.logger.error("Target time is already in the past.")
            return
        self._start_session(target, kind=SessionKind.MANUAL)
        # A manual timer still snaps to a sooner watch candidate if there is one.
        self._retarget_current_to_nearest()

    def _poll_calendar(self) -> None:
        if not self.config.calendar_enabled and not self.config.hard_stop_enabled:
            return
        elapsed = self.clock.monotonic() - self._last_cal_poll
        if elapsed < self.config.calendar_poll_seconds:
            return
        self._last_cal_poll = self.clock.monotonic()
        if self._current is None:
            self._start_from_nearest()
        else:
            self._retarget_current_to_nearest()

    # -- session control -----------------------------------------------------

    def _start_session(
        self,
        target: dt.datetime,
        *,
        kind: SessionKind,
        event_start: dt.datetime | None = None,
        event_id: str | None = None,
        event_title: str | None = None,
        call_url: str | None = None,
        room: str | None = None,
    ) -> None:
        if self._current is not None:
            self._current.stop()
        self._current = self.session_factory(
            target,
            kind=kind,
            event_start=event_start,
            event_id=event_id,
            event_title=event_title,
            call_url=call_url,
            room=room,
        )
        remaining = (target - self.clock.now()).total_seconds()
        suffix = ""
        if kind is SessionKind.HARD_STOP:
            suffix = f" · hard stop {target:%H:%M}"
        self.logger.info(
            f"Countdown → {target:%H:%M:%S} ({format_duration(remaining)} remaining){suffix}"
        )

    def _start_from_nearest(self) -> bool:
        if self._current is not None:
            return False
        candidate = self._nearest_candidate()
        if candidate is None:
            return False
        self._start_session(
            candidate.target,
            kind=candidate.kind,
            event_start=candidate.event_start,
            event_id=candidate.event_id,
            event_title=candidate.event_title,
            call_url=candidate.call_url,
            room=candidate.room,
        )
        return True

    def _retarget_current_to_nearest(self) -> None:
        """Snap the live session to a sooner watch candidate (edge-cases #14)."""
        if self._current is None:
            return
        candidate = self._nearest_candidate()
        if candidate is None:
            return
        session = self._current.session
        if abs((session.target - candidate.target).total_seconds()) <= _RETARGET_EPSILON_SECONDS:
            return
        if session.retarget(
            candidate.target,
            self.clock.now(),
            kind=candidate.kind,
            event_start=candidate.event_start,
            event_id=candidate.event_id,
            event_title=candidate.event_title,
            call_url=candidate.call_url,
            room=candidate.room,
        ):
            if candidate.kind is SessionKind.CALENDAR and candidate.event_title:
                self.logger.info(
                    f"Calendar → {candidate.target:%H:%M} ({candidate.event_title})"
                )
            elif candidate.kind is SessionKind.HARD_STOP:
                self.logger.info(f"Hard stop → {candidate.target:%H:%M}")

    def _nearest_candidate(self) -> _WatchCandidate | None:
        now = self.clock.now()
        candidates: list[_WatchCandidate] = []

        if self.config.calendar_enabled:
            event = self._pending_event()
            if event is not None:
                block_at = calendar_block_target(event.start, self.config, now)
                if block_at is not None:
                    candidates.append(
                        _WatchCandidate(
                            target=block_at,
                            kind=SessionKind.CALENDAR,
                            event_start=event.start,
                            event_id=event.event_id,
                            event_title=event.title,
                            call_url=event.call_url,
                            room=event.room,
                        )
                    )

        if self.config.hard_stop_enabled:
            stop_at = hard_stop_target(self.config, now)
            if stop_at is not None:
                candidates.append(
                    _WatchCandidate(
                        target=stop_at,
                        kind=SessionKind.HARD_STOP,
                    )
                )

        if not candidates:
            return None
        return min(candidates, key=lambda c: c.target)

    def _pending_event(self) -> CalendarEvent | None:
        """Nearest accepted event that has not already fired its block."""
        event = self.calendar.nearest_event_within(self.config.calendar_window_minutes)
        if event is None:
            return None
        if event.event_id in self._finished_events:
            if self.clock.now() >= event.start:
                self._finished_events.discard(event.event_id)
            else:
                return None
        return event
