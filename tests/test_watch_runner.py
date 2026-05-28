"""Tests for app.watch_runner — watch-mode orchestration via fakes."""

import datetime as dt

from ctimeli import ports
from ctimeli.app.session_runner import SessionRunner
from ctimeli.app.watch_runner import WatchRunner
from ctimeli.domain.calendar import CalendarEvent
from ctimeli.domain.config import AppConfig
from ctimeli.domain.session import Session, SessionKind

from .fakes import (
    FakeAppControl,
    FakeWorkspaceTidy,
    FakeCalendar,
    FakeClock,
    FakeInput,
    FakeOverlay,
    FakeScheduler,
    FakeScreenBlur,
    FakeSignals,
    FakeStopOverlay,
    FakeUrlOpener,
    FakeWatchMenuBar,
    FakeWifiSource,
    NullInputSource,
    RecordingLogger,
)

NOW = dt.datetime(2026, 5, 21, 14, 0, 0)


def _session_factory(clock, config=None, signals=None):
    """A factory that builds real SessionRunners wired to fakes."""

    def factory(target, *, kind, event_start, event_id, event_title, call_url, room):
        session = Session(
            started=clock.now(),
            target=target,
            config=config or AppConfig(),
            kind=kind,
            event_start=event_start,
            event_id=event_id,
            event_title=event_title,
            call_url=call_url,
            room=room,
        )
        return SessionRunner(
            session,
            clock=clock,
            logger=RecordingLogger(),
            scheduler=FakeScheduler(),
            overlay=FakeOverlay(),
            stop_overlay=FakeStopOverlay(),
            blur=FakeScreenBlur(),
            app_control=FakeAppControl(),
            workspace_tidy=FakeWorkspaceTidy(),
            signals=signals or FakeSignals(),
            url_opener=FakeUrlOpener(),
            wifi=FakeWifiSource(),
        )

    return factory


def make_watch(*, calendar_event=None, config=None, menu_bar=None):
    clock = FakeClock(NOW)
    cfg = config or AppConfig()
    mb = menu_bar or FakeWatchMenuBar()
    signals = FakeSignals()
    parts = {
        "config": cfg,
        "clock": clock,
        "logger": RecordingLogger(),
        "input_source": FakeInput(),
        "calendar": FakeCalendar(event=calendar_event),
        "signals": signals,
        "scheduler": FakeScheduler(),
        "app_control": FakeAppControl(),
        "menu_bar": mb,
        "session_factory": _session_factory(clock, cfg, signals),
    }
    return WatchRunner(**parts), parts


def test_quick_add_starts_a_session():
    watch, _ = make_watch()
    watch._try_start_manual(NOW + dt.timedelta(minutes=15))
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
    assert watch._start_from_nearest() is True
    assert watch._current is not None
    assert watch._current.session.kind is SessionKind.CALENDAR


def test_finished_calendar_event_is_not_restarted():
    event = CalendarEvent(
        event_id="evt-1", title="Standup", start=NOW + dt.timedelta(minutes=20)
    )
    watch, _ = make_watch(calendar_event=event)
    watch._finished_events["evt-1"] = NOW + dt.timedelta(minutes=20)
    # Event start is still in the future -> dedup suppresses it.
    assert watch._pending_event() is None
    assert watch._start_from_nearest() is False


def test_calendar_retarget_snaps_live_session():
    # A running manual session must snap when a sooner calendar event appears.
    cal = FakeCalendar(event=None)
    watch, parts = make_watch()
    watch.calendar = cal
    watch._try_start_manual(NOW + dt.timedelta(minutes=30))
    assert watch._current.session.kind is SessionKind.MANUAL
    cal.event = CalendarEvent(
        event_id="e1", title="Standup", start=NOW + dt.timedelta(minutes=20)
    )
    old_target = watch._current.session.target
    watch._sync_to_nearest_candidate(from_manual=False)
    # calendar_block_before_mins default is 7 → block_at = NOW+13min < NOW+30min
    assert watch._current.session.target < old_target
    assert watch._current.session.kind is SessionKind.CALENDAR
    assert any("CAL" in line and "→" in line for line in parts["logger"].info_lines)


def test_manual_start_trumped_by_later_calendar():
    event = CalendarEvent(
        event_id="e1", title="Standup", start=NOW + dt.timedelta(minutes=20)
    )
    watch, parts = make_watch(calendar_event=event)
    watch._try_start_manual(NOW + dt.timedelta(minutes=5))
    watch._current.pump()
    assert watch._current.session.kind is SessionKind.CALENDAR
    assert any("Priority" in line for line in parts["logger"].info_lines)


def test_extend_rejected_when_calendar_pending():
    cal = FakeCalendar(event=None)
    watch, parts = make_watch()
    watch.calendar = cal
    watch._try_start_manual(NOW + dt.timedelta(minutes=30))
    watch._current.pump()
    cal.event = CalendarEvent(
        event_id="e1", title="Meet", start=NOW + dt.timedelta(minutes=40)
    )
    old_target = watch._current.session.target
    watch._try_extend_manual(15)
    assert watch._current.session.target == old_target
    assert any("extend ignored" in line for line in parts["logger"].info_lines)


def test_extend_rejected_on_calendar_session():
    event = CalendarEvent(
        event_id="e1", title="Standup", start=NOW + dt.timedelta(minutes=20)
    )
    watch, _ = make_watch(calendar_event=event)
    watch._start_from_nearest()
    watch._current.pump()
    old_target = watch._current.session.target
    watch._try_extend_manual(15)
    assert watch._current.session.target == old_target


def test_extend_pure_manual_session():
    watch, parts = make_watch()
    watch._try_start_manual(NOW + dt.timedelta(minutes=10))
    watch._current.pump()
    old_target = watch._current.session.target
    watch._try_extend_manual(5)
    assert watch._current.session.target > old_target
    assert any("TIME" in line and "+5" in line for line in parts["logger"].info_lines)


def test_completed_calendar_session_adds_to_finished_events():
    # When a calendar session finishes via the block-on-end path (not interrupted),
    # its event_id must be added to _finished_events to prevent re-triggering.
    event = CalendarEvent(
        event_id="evt-fin", title="Meeting", start=NOW + dt.timedelta(minutes=20)
    )
    config = AppConfig(block_on_end=True)
    watch, parts = make_watch(calendar_event=event, config=config)
    assert watch._start_from_nearest() is True

    runner = watch._current
    runner.pump()                          # setup + first frame
    parts["clock"].advance(3600.0)         # jump past target
    runner.pump()                          # tick -> BLOCKING
    runner.stop_overlay.dismiss = True     # simulate user click
    runner.pump()                          # -> CLEANUP
    runner.pump()                          # cleanup -> DONE (returns False)

    watch._pump_current()                  # watch detects session done, checks conditions
    assert "evt-fin" in watch._finished_events


def test_finish_early_marks_calendar_event_finished():
    event = CalendarEvent(
        event_id="evt-early", title="Standup", start=NOW + dt.timedelta(minutes=20)
    )
    watch, _ = make_watch(calendar_event=event, config=AppConfig(block_on_end=False))
    assert watch._start_from_nearest() is True
    runner = watch._current
    runner.pump()
    runner.overlay.finish = True
    runner.pump()
    watch._pump_current()
    assert "evt-early" in watch._finished_events
    assert watch._start_from_nearest() is False


def test_sleep_abandon_marks_event_finished_and_goes_idle():
    first = CalendarEvent(
        event_id="evt-a", title="A", start=NOW + dt.timedelta(minutes=20)
    )
    watch, parts = make_watch(calendar_event=first)
    assert watch._start_from_nearest() is True
    runner = watch._current
    runner.pump()
    parts["clock"].advance_wall_only(60.0)
    runner.pump()
    watch._pump_current()
    assert "evt-a" in watch._finished_events
    assert watch._current is None
    assert watch._start_from_nearest() is False


def test_watch_survives_block_end_dismiss():
    watch, parts = make_watch(config=AppConfig(block_on_end=True))
    watch._try_start_manual(NOW + dt.timedelta(seconds=6))
    runner = watch._current
    runner.pump()
    parts["clock"].advance(10.0)
    runner.pump()                          # -> BLOCKING
    runner.stop_overlay.dismiss = True
    while runner.pump():
        parts["clock"].advance(0.02)
    watch._pump_current()
    assert watch._current is None
    assert watch._tick_once() is True


def test_watch_survives_sigint_during_block_end():
    watch, parts = make_watch(config=AppConfig(block_on_end=True))
    watch._try_start_manual(NOW + dt.timedelta(minutes=1))
    runner = watch._current
    runner.pump()
    parts["clock"].advance(3600.0)
    runner.pump()                          # -> BLOCKING
    parts["signals"].trigger()             # Ctrl+C during block (shared listener)
    while runner.pump():
        parts["clock"].advance(0.02)
    watch._pump_current()
    assert watch._current is None
    assert not parts["signals"].interrupted()
    assert watch._tick_once() is True


def test_watch_skips_calendar_queries_when_access_denied():
    cal = FakeCalendar(access=False)
    watch, parts = make_watch()
    watch.calendar = cal
    watch._announce()
    assert watch._calendar_available is False
    nearest_before = cal.nearest_calls
    watch._try_start_manual(NOW + dt.timedelta(minutes=5))
    for _ in range(30):
        watch._tick_once(yield_loop=False)
    assert cal.nearest_calls == nearest_before
    assert cal.access_calls == 1


def test_interrupt_signal_exits_watch_run_loop():
    watch, parts = make_watch()
    parts["signals"]._interrupted = True   # pre-fire Ctrl+C
    exit_code = watch.run()
    assert exit_code == 0
    assert parts["input_source"].close_calls == 1
    assert parts["signals"].restored is True
    assert parts["menu_bar"].torn_down is True


def test_run_loop_exits_on_menu_quit():
    watch, parts = make_watch()
    parts["menu_bar"].feed(ports.WatchMenuAction(kind="quit"))
    exit_code = watch.run()
    assert exit_code == 0
    assert parts["signals"].installed is True
    assert parts["signals"].restored is True
    assert parts["menu_bar"].torn_down is True
    assert parts["scheduler"].stopped is True


def test_run_loop_survives_input_eof():
    watch, parts = make_watch()
    parts["input_source"].set_closed()
    parts["menu_bar"].feed(ports.WatchMenuAction(kind="quit"))
    assert watch.run() == 0


def test_menu_start_starts_session():
    watch, parts = make_watch()
    parts["menu_bar"].feed(ports.WatchMenuAction(kind="start_minutes", minutes=15))
    watch._poll_menu()
    assert watch._current is not None
    assert watch._current.session.kind is SessionKind.MANUAL


def test_update_menu_bar_extend_disabled_for_calendar():
    event = CalendarEvent(
        event_id="e1", title="Standup", start=NOW + dt.timedelta(minutes=20)
    )
    menu_bar = FakeWatchMenuBar()
    watch, _ = make_watch(calendar_event=event, menu_bar=menu_bar)
    watch._start_from_nearest()
    watch._update_menu_bar()
    assert menu_bar.idle is False
    assert menu_bar.extend_enabled is False


def test_update_menu_bar_does_not_query_calendar_every_frame():
    watch, parts = make_watch()
    watch._try_start_manual(NOW + dt.timedelta(minutes=10))
    watch._refresh_calendar_trump()
    nearest_before = parts["calendar"].nearest_calls
    for _ in range(30):
        watch._update_menu_bar()
    assert parts["calendar"].nearest_calls == nearest_before


def test_hard_stop_auto_starts_when_enabled():
    config = AppConfig(
        hard_stop_enabled=True,
        hard_stop_time=dt.time(22, 0),
        hard_stop_warning_mins=30.0,
        calendar_enabled=False,
    )
    clock = FakeClock(dt.datetime(2026, 5, 21, 21, 45, 0))
    watch = WatchRunner(
        config=config,
        clock=clock,
        logger=RecordingLogger(),
        input_source=FakeInput(),
        calendar=FakeCalendar(event=None),
        signals=FakeSignals(),
        scheduler=FakeScheduler(),
        app_control=FakeAppControl(),
        menu_bar=FakeWatchMenuBar(),
        session_factory=_session_factory(clock, config),
    )
    assert watch._start_from_nearest() is True
    assert watch._current.session.kind is SessionKind.HARD_STOP


def test_evict_stale_finished_clears_past_entries():
    watch, parts = make_watch()
    # Seed finished_events with one past and one future entry.
    past_start = NOW - dt.timedelta(hours=2)
    future_start = NOW + dt.timedelta(minutes=30)
    watch._finished_events["old-evt"] = past_start
    watch._finished_events["future-evt"] = future_start
    watch._evict_stale_finished()
    assert "old-evt" not in watch._finished_events
    assert "future-evt" in watch._finished_events


def test_evict_called_during_calendar_poll():
    # After the poll interval, stale entries are swept even when the calendar
    # returns a different nearest event (the path that previously left them stuck).
    config = AppConfig(calendar_poll_seconds=15.0)
    watch, parts = make_watch(config=config)
    past_start = NOW - dt.timedelta(hours=1)
    watch._finished_events["stale-evt"] = past_start
    # Advance past the poll interval so _poll_calendar runs.
    parts["clock"].advance(20.0)
    watch._poll_calendar()
    assert "stale-evt" not in watch._finished_events


def test_hard_stop_wins_when_sooner_than_calendar():
    event = CalendarEvent(
        event_id="evt-1",
        title="Late meeting",
        start=NOW + dt.timedelta(hours=2),
    )
    config = AppConfig(
        hard_stop_enabled=True,
        hard_stop_time=dt.time(14, 15),
        hard_stop_warning_mins=30.0,
    )
    clock = FakeClock(NOW)
    watch = WatchRunner(
        config=config,
        clock=clock,
        logger=RecordingLogger(),
        input_source=FakeInput(),
        calendar=FakeCalendar(event=event),
        signals=FakeSignals(),
        scheduler=FakeScheduler(),
        app_control=FakeAppControl(),
        menu_bar=FakeWatchMenuBar(),
        session_factory=_session_factory(clock, config),
    )
    assert watch._start_from_nearest() is True
    assert watch._current.session.kind is SessionKind.HARD_STOP


def test_watch_requests_accessibility_when_block_on_end():
    tidy = FakeWorkspaceTidy()
    cfg = AppConfig(block_on_end=True)
    watch, _ = make_watch(config=cfg)
    watch._workspace_tidy = tidy
    watch._announce()
    assert tidy.access_calls == 1


def test_watch_skips_accessibility_when_block_on_end_off():
    tidy = FakeWorkspaceTidy()
    cfg = AppConfig(block_on_end=False)
    watch, _ = make_watch(config=cfg)
    watch._workspace_tidy = tidy
    watch._announce()
    assert tidy.access_calls == 0


def test_null_input_never_eof():
    src = NullInputSource()
    assert src.closed() is False
    assert src.poll_lines() == []
