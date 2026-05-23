"""Tests for domain.session — the transition table in docs/domain.md section 7."""

import datetime as dt

from countdown.domain.colors import STROKE_BLUE
from countdown.domain.config import AppConfig
from countdown.domain.session import Session, SessionKind, SessionState

STARTED = dt.datetime(2026, 5, 21, 14, 0, 0)
FRAME = 1.0 / 60.0


def make_session(*, block_on_end=False, duration=60.0, kind=SessionKind.MANUAL, **kw):
    cfg = AppConfig(block_on_end=block_on_end)
    target = STARTED + dt.timedelta(seconds=duration)
    return Session(started=STARTED, target=target, config=cfg, kind=kind, **kw)


def test_starts_pending_then_running():
    session = make_session()
    assert session.state is SessionState.PENDING
    session.start()
    assert session.state is SessionState.RUNNING


def test_tick_before_zero_stays_running():
    session = make_session(duration=60.0)
    session.start()
    frame = session.tick(STARTED + dt.timedelta(seconds=30), FRAME)
    assert session.state is SessionState.RUNNING
    assert 0.0 < frame.fraction <= 1.0


def test_zero_without_block_is_done():
    session = make_session(block_on_end=False, duration=10.0)
    session.start()
    session.tick(STARTED + dt.timedelta(seconds=20), FRAME)
    assert session.state is SessionState.DONE


def test_zero_with_block_is_blocking():
    session = make_session(block_on_end=True, duration=10.0)
    session.start()
    session.tick(STARTED + dt.timedelta(seconds=20), FRAME)
    assert session.state is SessionState.BLOCKING
    assert session.blocked is True


def test_finish_matches_zero_behaviour():
    plain = make_session(block_on_end=False)
    plain.start()
    plain.finish()
    assert plain.state is SessionState.DONE

    blocking = make_session(block_on_end=True)
    blocking.start()
    blocking.finish()
    assert blocking.state is SessionState.BLOCKING


def test_retarget_grows_total_but_never_shrinks_it():
    session = make_session(duration=60.0)
    session.start()
    original_total = session.total_seconds

    # Pull the target out: total grows.
    session.retarget(STARTED + dt.timedelta(seconds=120), STARTED + dt.timedelta(seconds=5))
    assert session.total_seconds == 120.0

    # Pull the target in: total must NOT shrink (the key invariant).
    session.retarget(STARTED + dt.timedelta(seconds=30), STARTED + dt.timedelta(seconds=5))
    assert session.total_seconds == 120.0
    assert session.target == STARTED + dt.timedelta(seconds=30)
    assert original_total == 60.0


def test_retarget_into_the_past_is_ignored():
    session = make_session(duration=60.0)
    session.start()
    applied = session.retarget(
        STARTED + dt.timedelta(seconds=5), STARTED + dt.timedelta(seconds=10)
    )
    assert applied is False


def test_interrupt_from_running_is_terminal():
    session = make_session()
    session.start()
    session.interrupt()
    assert session.state is SessionState.INTERRUPTED
    assert session.interrupted is True


def test_interrupt_while_blocking_routes_through_cleanup():
    session = make_session(block_on_end=True, duration=5.0)
    session.start()
    session.tick(STARTED + dt.timedelta(seconds=10), FRAME)  # -> BLOCKING
    session.interrupt()
    assert session.state is SessionState.CLEANUP
    assert session.interrupted is True


def test_dismiss_and_cleaned_path():
    session = make_session(block_on_end=True, duration=5.0)
    session.start()
    session.tick(STARTED + dt.timedelta(seconds=10), FRAME)  # -> BLOCKING
    session.dismiss()
    assert session.state is SessionState.CLEANUP
    session.cleaned()
    assert session.state is SessionState.DONE


def test_terminal_states_ignore_events():
    session = make_session()
    session.start()
    session.interrupt()  # -> INTERRUPTED
    session.finish()
    session.dismiss()
    session.interrupt()
    assert session.state is SessionState.INTERRUPTED


def test_retarget_updates_kind_and_event_metadata():
    session = make_session(duration=120.0, kind=SessionKind.MANUAL)
    session.start()
    event_start = STARTED + dt.timedelta(seconds=90)
    applied = session.retarget(
        STARTED + dt.timedelta(seconds=60),
        STARTED + dt.timedelta(seconds=5),
        kind=SessionKind.CALENDAR,
        event_start=event_start,
        event_id="evt-1",
        event_title="Standup",
    )
    assert applied is True
    assert session.kind is SessionKind.CALENDAR
    assert session.event_id == "evt-1"
    assert session.event_title == "Standup"
    assert session.event_start == event_start


def test_base_color_by_kind():
    assert make_session(kind=SessionKind.MANUAL).base_color == STROKE_BLUE
    cal = make_session(kind=SessionKind.CALENDAR)
    assert cal.base_color.g == cal.config.calendar_stroke_g


def test_remote_call_skips_block_off_work_wifi():
    session = make_session(
        block_on_end=True,
        duration=10.0,
        kind=SessionKind.CALENDAR,
        call_url="https://zoom.us/j/123",
    )
    session.start()
    session.tick(STARTED + dt.timedelta(seconds=20), FRAME, on_work_wifi=False)
    assert session.state is SessionState.DONE
    assert session.blocked is False


def test_remote_call_on_work_wifi_still_blocks():
    session = make_session(
        block_on_end=True,
        duration=10.0,
        kind=SessionKind.CALENDAR,
        call_url="https://zoom.us/j/123",
    )
    session.start()
    session.tick(STARTED + dt.timedelta(seconds=20), FRAME, on_work_wifi=True)
    assert session.state is SessionState.BLOCKING


def test_room_calendar_still_blocks_on_end():
    session = make_session(
        block_on_end=True,
        duration=10.0,
        kind=SessionKind.CALENDAR,
        call_url="https://zoom.us/j/123",
        room="Room 4B",
    )
    session.start()
    session.tick(STARTED + dt.timedelta(seconds=20), FRAME)
    assert session.state is SessionState.BLOCKING


def test_hard_stop_base_color_and_label():
    cfg = AppConfig(hard_stop_stroke_g=0.55)
    target = STARTED + dt.timedelta(minutes=12, seconds=4)
    session = Session(
        started=STARTED,
        target=target,
        config=cfg,
        kind=SessionKind.HARD_STOP,
    )
    session.start()
    frame = session.tick(STARTED + dt.timedelta(seconds=10), FRAME)
    assert session.base_color.r == cfg.hard_stop_stroke_r
    assert "hard stop" in frame.label


def test_calendar_label_has_event_suffix():
    event_start = STARTED + dt.timedelta(hours=1)
    session = make_session(kind=SessionKind.CALENDAR, event_start=event_start)
    session.start()
    frame = session.tick(STARTED + dt.timedelta(seconds=10), FRAME)
    assert "·" in frame.label
