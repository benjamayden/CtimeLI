"""Tests for app.watch_runner — watch-mode orchestration via fakes."""

import datetime as dt

from countdown.app.session_runner import SessionRunner
from countdown.app.watch_runner import WatchRunner
from countdown.domain.calendar import CalendarEvent
from countdown.domain.config import AppConfig
from countdown.domain.session import Session, SessionKind

from .fakes import (
    FakeAppControl,
    FakeBlockExecutor,
    FakeCalendar,
    FakeClock,
    FakeInput,
    FakeOverlay,
    FakeScheduler,
    FakeShaker,
    FakeSignals,
    FakeStopOverlay,
    RecordingLogger,
)

NOW = dt.datetime(2026, 5, 21, 14, 0, 0)


def _session_factory(clock):
    """A factory that builds real SessionRunners wired to fakes."""

    def factory(target, *, kind, event_start, event_id, event_title):
        session = Session(
            started=clock.now(),
            target=target,
            config=AppConfig(),
            kind=kind,
            event_start=event_start,
            event_id=event_id,
            event_title=event_title,
        )
        return SessionRunner(
            session,
            clock=clock,
            logger=RecordingLogger(),
            scheduler=FakeScheduler(),
            overlay=FakeOverlay(),
            stop_overlay=FakeStopOverlay(),
            shaker=FakeShaker(),
            app_control=FakeAppControl(),
            block_executor=FakeBlockExecutor(),
            signals=FakeSignals(),
        )

    return factory


def make_watch(*, calendar_event=None, config=None):
    clock = FakeClock(NOW)
    parts = {
        "config": config or AppConfig(),
        "clock": clock,
        "logger": RecordingLogger(),
        "input_source": FakeInput(),
        "calendar": FakeCalendar(event=calendar_event),
        "signals": FakeSignals(),
        "scheduler": FakeScheduler(),
        "app_control": FakeAppControl(),
        "session_factory": _session_factory(clock),
    }
    return WatchRunner(**parts), parts


def test_quick_add_starts_a_session():
    watch, _ = make_watch()
    watch._handle_line("15")
    assert watch._current is not None
    assert watch._current.session.kind is SessionKind.MANUAL


def test_quit_word_sets_quit():
    watch, _ = make_watch()
    watch._handle_line("q")
    assert watch._quit is True


def test_bad_input_is_reported_not_started():
    watch, parts = make_watch()
    watch._handle_line("definitely not a time")
    assert watch._current is None
    assert parts["logger"].error_lines


def test_calendar_event_auto_starts():
    event = CalendarEvent(
        event_id="evt-1", title="Standup", start=NOW + dt.timedelta(minutes=20)
    )
    watch, _ = make_watch(calendar_event=event)
    assert watch._start_from_nearest_event() is True
    assert watch._current is not None
    assert watch._current.session.kind is SessionKind.CALENDAR


def test_finished_calendar_event_is_not_restarted():
    event = CalendarEvent(
        event_id="evt-1", title="Standup", start=NOW + dt.timedelta(minutes=20)
    )
    watch, _ = make_watch(calendar_event=event)
    watch._finished_events.add("evt-1")
    # Event start is still in the future -> dedup suppresses it.
    assert watch._pending_event() is None
    assert watch._start_from_nearest_event() is False


def test_run_loop_exits_on_quit_input():
    watch, parts = make_watch()
    parts["input_source"].feed("q")
    exit_code = watch.run()
    assert exit_code == 0
    assert parts["signals"].installed is True
    assert parts["signals"].restored is True
    assert parts["input_source"].close_calls == 1
    assert parts["scheduler"].stopped is True


def test_run_loop_exits_on_eof():
    watch, parts = make_watch()
    parts["input_source"].set_closed()
    assert watch.run() == 0
