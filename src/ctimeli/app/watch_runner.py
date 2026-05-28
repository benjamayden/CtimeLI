"""WatchRunner — the long-lived watch-mode loop.

Listens for menu bar actions and calendar events; spawns and retargets a
SessionRunner. Like SessionRunner it is written against ports and a session
factory, so it is testable with fakes.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Protocol

from ctimeli import ports
from ctimeli.domain.calendar import CalendarEvent, calendar_block_target, hard_stop_target
from ctimeli.domain.config import AppConfig
from ctimeli.domain.math import format_duration, format_duration_compact
from ctimeli.terminal_ui import indent, ok, skip, tagged
from ctimeli.domain.session import FRAME_INTERVAL, SessionKind, SessionState
from ctimeli.domain.timespec import parse_quick_input

from .session_runner import SessionRunner

# Below this difference a calendar target is "the same" — do not retarget.
_RETARGET_EPSILON_SECONDS = 1.0
# Longer pump while idle so status-bar menus and alerts get event time.
_IDLE_PUMP_INTERVAL = 0.1


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
    """Drives watch mode: menu bar quick-add + calendar auto-start / snap."""

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
        menu_bar: ports.WatchMenuBar,
        session_factory: SessionFactory,
        workspace_tidy: ports.WorkspaceTidy | None = None,
    ) -> None:
        self.config = config
        self.clock = clock
        self.logger = logger
        self.input_source = input_source
        self.calendar = calendar
        self.signals = signals
        self.scheduler = scheduler
        self.app_control = app_control
        self.menu_bar = menu_bar
        self.session_factory = session_factory
        self._workspace_tidy = workspace_tidy
        self._current: SessionRunner | None = None
        self._quit = False
        self._last_cal_poll = 0.0
        # Maps fired event_id → event_start so stale entries can be evicted once
        # the event's start time passes (edge-cases #29).
        self._finished_events: dict[str, dt.datetime] = {}
        self._calendar_trumps_manual = False
        self._calendar_available = True

    def run(self) -> int:
        """Run the watch loop until the user quits. Returns an exit code."""
        self._startup()
        try:
            self._announce()
            while self._tick_once():
                pass
        finally:
            self._shutdown()
        return 0

    def _startup(self) -> None:
        self.signals.install()
        self.menu_bar.show()
        self._go_idle()

    def _tick_once(self, *, pump_idle: bool = True, yield_loop: bool = True) -> bool:
        if self._quit:
            return False
        if self._current is None and self.signals.interrupted():
            return False
        self._poll_input()
        self._poll_menu()
        self._poll_calendar()
        self._pump_current(pump_idle=pump_idle, yield_loop=yield_loop)
        if not self.menu_bar.is_menu_open():
            self._update_menu_bar()
        return True

    def tick_interval(self) -> float:
        if self._current is None:
            return _IDLE_PUMP_INTERVAL
        if self._current.session.state is SessionState.BLOCKING:
            return 0.05
        return FRAME_INTERVAL

    # -- startup / shutdown --------------------------------------------------

    def _announce(self) -> None:
        self._calendar_available = True
        if self.config.calendar_enabled:
            self._calendar_available = self.calendar.ensure_access()
            self._last_cal_poll = self.clock.monotonic()
        if self.config.block_on_end and self._workspace_tidy is not None:
            self._workspace_tidy.ensure_access()
        if self._calendar_available and not self._start_from_nearest():
            self.logger.info(tagged("CAL", "No upcoming events in window."))
        elif self.config.calendar_enabled and not self._calendar_available:
            self.logger.info(skip("Calendar off — auto-start disabled."))
        self._refresh_calendar_trump()
        self.logger.info(tagged("WATCH", "Ready — click the menu bar icon."))
        self.logger.info(indent("Start a timer or quit from there."))
        if self.config.block_on_end:
            self.logger.info(indent("At zero: dismiss the stop screen to tidy windows."))

    def _shutdown(self) -> None:
        if self._current is not None:
            self._current.session.interrupt()
            while self._current.pump():
                pass
            self._current = None
        self.menu_bar.teardown()
        self.input_source.close()
        self.signals.restore()
        self.scheduler.stop()

    def _go_idle(self) -> None:
        self.app_control.set_activation_policy(ports.ActivationPolicy.ACCESSORY)

    # -- per-loop steps ------------------------------------------------------

    def _pump_current(self, *, pump_idle: bool = True, yield_loop: bool = True) -> None:
        if self._current is None:
            if pump_idle:
                self.scheduler.pump(_IDLE_PUMP_INTERVAL)
            return
        if self._current.pump(yield_loop=yield_loop):
            return
        session = self._current.session
        if (
            session.kind is SessionKind.CALENDAR
            and session.event_id
            and session.state is SessionState.DONE
            and not session.interrupted
        ):
            self._finished_events[session.event_id] = session.event_start or session.target
        abandoned_sleep = session.abandoned_for_sleep
        self._current = None
        self._go_idle()
        if abandoned_sleep:
            self._start_from_nearest()
        if self.signals.interrupted():
            # Session consumed SIGINT for block-end tidy — do not quit watch.
            self.signals.clear()

    def _poll_input(self) -> None:
        for line in self.input_source.poll_lines():
            self._handle_line(line)

    def _poll_menu(self) -> None:
        for action in self.menu_bar.poll_actions():
            if action.kind == "quit":
                self._quit = True
            elif action.kind == "start_minutes":
                target = self.clock.now() + dt.timedelta(minutes=action.minutes)
                self._try_start_manual(target)
            elif action.kind == "extend_minutes":
                self._try_extend_manual(action.minutes)

    def _update_menu_bar(self) -> None:
        if self._current is None:
            self.menu_bar.set_status(label=None)
            self.menu_bar.set_idle(True)
            self.menu_bar.set_extend_enabled(True)
            return
        session = self._current.session
        remaining = max(0.0, (session.target - self.clock.now()).total_seconds())
        self.menu_bar.set_status(label=format_duration_compact(remaining))
        self.menu_bar.set_idle(False)
        extend_ok = (
            session.kind is SessionKind.MANUAL and not self._calendar_trumps_manual
        )
        self.menu_bar.set_extend_enabled(extend_ok)

    def _refresh_calendar_trump(self) -> None:
        """Update extend/menu state from calendar poll — not every frame."""
        if not self.config.calendar_enabled and not self.config.hard_stop_enabled:
            self._calendar_trumps_manual = False
            return
        if self.config.calendar_enabled and not self._calendar_available:
            if not self.config.hard_stop_enabled:
                self._calendar_trumps_manual = False
                return
        self._calendar_trumps_manual = self._nearest_candidate() is not None

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
        self._try_start_manual(target)

    def _try_start_manual(self, target: dt.datetime) -> None:
        self._start_session(target, kind=SessionKind.MANUAL)
        if self._current is not None:
            self._current.pump()
        self._sync_to_nearest_candidate(from_manual=True)

    def _try_extend_manual(self, minutes: float) -> None:
        if self._current is None:
            return
        session = self._current.session
        if session.kind is not SessionKind.MANUAL:
            return
        self._refresh_calendar_trump()
        if self._calendar_trumps_manual:
            self.logger.info(skip("Calendar has priority — extend ignored."))
            return
        new_target = session.target + dt.timedelta(minutes=minutes)
        if session.retarget(new_target, self.clock.now()):
            self.logger.info(
                tagged("TIME", f"+{minutes:g}m → ends {new_target:%H:%M:%S}")
            )

    def _evict_stale_finished(self) -> None:
        now = self.clock.now()
        stale = [eid for eid, start in self._finished_events.items() if now >= start]
        for eid in stale:
            del self._finished_events[eid]

    def _poll_calendar(self) -> None:
        if not self.config.calendar_enabled and not self.config.hard_stop_enabled:
            return
        elapsed = self.clock.monotonic() - self._last_cal_poll
        if elapsed < self.config.calendar_poll_seconds:
            return
        self._last_cal_poll = self.clock.monotonic()
        self._evict_stale_finished()
        self._refresh_calendar_trump()
        if self._current is None:
            self._start_from_nearest()
        else:
            self._sync_to_nearest_candidate(from_manual=False)

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
            tagged(
                "TIME",
                f"Ends {target:%H:%M:%S} ({format_duration(remaining)} left){suffix}",
            )
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

    def _sync_to_nearest_candidate(self, *, from_manual: bool) -> None:
        """Align the live session with calendar/hard-stop candidates."""
        if self._current is None:
            return
        candidate = self._nearest_candidate()
        if candidate is None:
            return
        session = self._current.session
        if abs((session.target - candidate.target).total_seconds()) <= _RETARGET_EPSILON_SECONDS:
            return
        if session.kind is SessionKind.MANUAL:
            should_sync = True
        else:
            should_sync = candidate.target < session.target
        if not should_sync:
            return
        was_manual = session.kind is SessionKind.MANUAL
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
            self._log_candidate_sync(candidate, priority=from_manual and was_manual)

    def _log_candidate_sync(self, candidate: _WatchCandidate, *, priority: bool) -> None:
        if candidate.kind is SessionKind.CALENDAR and candidate.event_title:
            title = candidate.event_title
            when = candidate.target.strftime("%H:%M")
            if priority:
                self.logger.info(tagged("CAL", f"Priority → {when} ({title})"))
            else:
                self.logger.info(tagged("CAL", f"→ {when} ({title})"))
        elif candidate.kind is SessionKind.HARD_STOP:
            when = candidate.target.strftime("%H:%M")
            if priority:
                self.logger.info(tagged("CAL", f"Hard stop priority → {when}"))
            else:
                self.logger.info(tagged("CAL", f"Hard stop → {when}"))

    def _nearest_candidate(self) -> _WatchCandidate | None:
        now = self.clock.now()
        candidates: list[_WatchCandidate] = []

        if self.config.calendar_enabled and self._calendar_available:
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
                del self._finished_events[event.event_id]
            else:
                return None
        return event
