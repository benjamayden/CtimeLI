"""Tests for app.session_runner — orchestration via fake adapters."""

import datetime as dt

from ctimeli import ports
from ctimeli.app.session_runner import SessionRunner
from ctimeli.domain.apps import AppSelector, RunningApp
from ctimeli.domain.config import AppConfig
from ctimeli.domain.session import Session, SessionKind, SessionState

from .fakes import (
    FakeAppControl,
    FakeClock,
    FakeOverlay,
    FakeScheduler,
    FakeScreenBlur,
    FakeSignals,
    FakeStopOverlay,
    FakeUrlOpener,
    FakeWifiSource,
    FakeWorkspaceTidy,
    RecordingLogger,
)

STARTED = dt.datetime(2026, 5, 21, 14, 0, 0)


class Harness:
    """A SessionRunner wired to fakes, with the fakes kept for assertions."""

    def __init__(
        self,
        *,
        block_on_end=False,
        duration=2.0,
        kind=SessionKind.MANUAL,
        call_url=None,
        room=None,
        work_ssids=frozenset(),
        wifi_ssid=None,
    ):
        cfg = AppConfig(block_on_end=block_on_end, work_wifi_ssids=work_ssids)
        target = STARTED + dt.timedelta(seconds=duration)
        self.session = Session(
            started=STARTED,
            target=target,
            config=cfg,
            kind=kind,
            call_url=call_url,
            room=room,
        )
        self.clock = FakeClock(STARTED)
        self.logger = RecordingLogger()
        self.scheduler = FakeScheduler()
        self.overlay = FakeOverlay()
        self.stop_overlay = FakeStopOverlay()
        self.blur = FakeScreenBlur()
        self.url_opener = FakeUrlOpener()
        self.wifi = FakeWifiSource(wifi_ssid)
        _notes = RunningApp(bundle_id="com.apple.Notes", display_name="Notes")
        self.app_control = FakeAppControl(
            frontmost=42,
            running=[_notes],
            apps_by_pid={42: _notes},
        )
        self.workspace_tidy = FakeWorkspaceTidy()
        self.signals = FakeSignals()
        self.runner = SessionRunner(
            self.session,
            clock=self.clock,
            logger=self.logger,
            scheduler=self.scheduler,
            overlay=self.overlay,
            stop_overlay=self.stop_overlay,
            blur=self.blur,
            app_control=self.app_control,
            workspace_tidy=self.workspace_tidy,
            signals=self.signals,
            url_opener=self.url_opener,
            wifi=self.wifi,
        )


def test_setup_shows_overlay_and_renders_a_frame():
    h = Harness(duration=60.0)
    assert h.runner.pump() is True
    assert h.overlay.shown is True
    assert ports.ActivationPolicy.ACCESSORY in h.app_control.policies
    assert len(h.overlay.frames) == 1


def test_runs_to_completion_without_block():
    h = Harness(block_on_end=False, duration=2.0)
    h.runner.pump()  # setup + first frame
    h.clock.advance(5.0)  # past the target
    assert h.runner.pump() is False
    assert h.session.state is SessionState.DONE
    assert h.overlay.torn_down is True
    assert h.scheduler.stopped is True


def test_block_on_end_enters_stop_overlay():
    h = Harness(block_on_end=True, duration=2.0)
    h.runner.pump()
    h.clock.advance(5.0)
    h.runner.pump()  # tick at zero -> BLOCKING
    assert h.session.state is SessionState.BLOCKING
    assert h.overlay.hidden is True
    assert h.stop_overlay.shown_lines is not None
    assert ports.ActivationPolicy.REGULAR in h.app_control.policies


def test_block_on_end_dismiss_runs_cleanup():
    h = Harness(block_on_end=True, duration=2.0)
    h.runner.pump()
    h.clock.advance(5.0)
    h.runner.pump()  # -> BLOCKING
    h.stop_overlay.dismiss = True
    assert h.runner.pump() is False  # dismiss -> CLEANUP -> DONE in one pump
    assert h.workspace_tidy.tidy_calls
    assert h.session.state is SessionState.DONE
    assert any("Block end" in line for line in h.logger.info_lines)


def test_finish_button_ends_the_session():
    h = Harness(block_on_end=False, duration=60.0)
    h.runner.pump()
    h.overlay.finish = True
    assert h.runner.pump() is False
    assert h.session.state is SessionState.DONE


def test_interrupt_ends_the_session():
    h = Harness(block_on_end=False, duration=60.0)
    h.runner.pump()
    h.signals.trigger()
    assert h.runner.pump() is False
    assert h.session.state is SessionState.INTERRUPTED


def test_blur_is_applied_during_countdown():
    h = Harness(duration=2.0, block_on_end=False)
    h.runner.pump()
    assert h.blur.shown is True
    assert h.blur.intensities  # blur ramps during the pulse window


def test_blur_persists_through_block_and_hides_on_cleanup():
    h = Harness(block_on_end=True, duration=2.0)
    h.runner.pump()
    h.clock.advance(5.0)
    h.runner.pump()  # -> BLOCKING
    assert h.blur.intensities[-1] == 1.0
    assert h.blur.hidden is False
    h.stop_overlay.dismiss = True
    h.runner.pump()  # -> CLEANUP (dismiss only)
    h.runner.pump()  # cleanup runs -> DONE
    assert h.blur.hidden is True


def test_interrupt_while_blocking_still_runs_cleanup():
    # Ctrl+C during BLOCKING must route through CLEANUP so windows are still tidied
    # (documented invariant in docs/domain.md §7 — no runner test existed for this).
    h = Harness(block_on_end=True, duration=2.0)
    h.runner.pump()
    h.clock.advance(5.0)
    h.runner.pump()       # tick at zero -> BLOCKING
    h.signals.trigger()   # Ctrl+C fires
    h.runner.pump()       # interrupt() -> CLEANUP (not INTERRUPTED)
    h.runner.pump()       # CLEANUP runs -> DONE
    assert h.session.state is SessionState.DONE
    assert h.workspace_tidy.tidy_calls
    assert h.session.interrupted is True


def test_finish_button_with_block_on_end_enters_blocking():
    # Finish button must honour block_on_end (features.md §6).
    h = Harness(block_on_end=True, duration=60.0)
    h.runner.pump()
    h.overlay.finish = True
    h.runner.pump()       # finish() -> BLOCKING
    assert h.session.state is SessionState.BLOCKING
    assert h.stop_overlay.shown_lines is not None
    assert h.overlay.hidden is True


def test_cleanup_activates_prior_app_before_tidy():
    h = Harness(block_on_end=True, duration=2.0)
    _safari = RunningApp(bundle_id="com.apple.Safari", display_name="Safari")
    new_ctrl = FakeAppControl(
        frontmost=77, running=[], apps_by_pid={77: _safari}
    )
    h.runner.app_control = new_ctrl
    h.runner.pump()
    h.clock.advance(5.0)
    h.runner.pump()       # -> BLOCKING (captures frontmost pid 77)
    h.stop_overlay.dismiss = True
    h.runner.pump()       # -> CLEANUP
    h.runner.pump()       # cleanup runs -> DONE
    assert new_ctrl.activated_pids == [77]


def test_cleanup_activates_prior_app_pid_during_tidy():
    h = Harness(block_on_end=True, duration=2.0)
    h.runner.pump()
    h.clock.advance(5.0)
    h.runner.pump()  # -> BLOCKING (captures frontmost pid 42 = "Notes")
    h.stop_overlay.dismiss = True
    h.runner.pump()  # -> CLEANUP
    h.runner.pump()  # cleanup runs
    # Prior app (pid 42) is activated before the tidy so the tidy operates on it.
    assert 42 in h.app_control.activated_pids


def test_skipped_app_regains_focus_after_cleanup():
    _terminal = RunningApp(bundle_id="com.apple.Terminal", display_name="Terminal")
    h = Harness(block_on_end=True, duration=2.0)
    h.runner.extra_skip = frozenset({AppSelector(kind="display_name", value="Terminal")})
    h.runner.app_control = FakeAppControl(
        frontmost=99,
        running=[_terminal],
        apps_by_pid={99: _terminal},
    )
    h.runner.pump()
    h.clock.advance(5.0)
    h.runner.pump()
    h.stop_overlay.dismiss = True
    h.runner.pump()
    h.runner.pump()
    # Skip app is activated twice: once before tidy, once in _restore_focus.
    assert h.runner.app_control.activated_pids == [99, 99]
    skip, _pump = h.workspace_tidy.tidy_calls[-1]
    assert skip == frozenset({AppSelector(kind="display_name", value="Terminal")})


def test_remote_call_opens_url_and_skips_stop_overlay():
    h = Harness(
        block_on_end=True,
        duration=2.0,
        kind=SessionKind.CALENDAR,
        call_url="https://zoom.us/j/123",
    )
    h.runner.pump()
    h.clock.advance(5.0)
    h.runner.pump()
    assert h.session.state is SessionState.DONE
    assert h.url_opener.opened == ["https://zoom.us/j/123"]
    assert h.stop_overlay.shown_lines is None
    assert any("Opened call link" in line for line in h.logger.info_lines)


def test_remote_call_on_work_wifi_blocks_without_opening_url():
    h = Harness(
        block_on_end=True,
        duration=2.0,
        kind=SessionKind.CALENDAR,
        call_url="https://zoom.us/j/123",
        work_ssids=frozenset({"Office"}),
        wifi_ssid="Office",
    )
    h.runner.pump()
    h.clock.advance(5.0)
    h.runner.pump()
    assert h.session.state is SessionState.BLOCKING
    assert h.url_opener.opened == []
    assert h.stop_overlay.shown_lines is not None


def test_room_calendar_shows_room_on_stop_overlay():
    h = Harness(
        block_on_end=True,
        duration=2.0,
        kind=SessionKind.CALENDAR,
        room="Room 4B",
    )
    h.runner.pump()
    h.clock.advance(5.0)
    h.runner.pump()
    assert h.stop_overlay.shown_lines is not None
    assert any("Room 4B" in line for line in h.stop_overlay.shown_lines)


def test_hard_stop_shows_hard_stop_overlay_lines():
    cfg = AppConfig(block_on_end=True, hard_stop_stroke_g=0.55)
    target = STARTED + dt.timedelta(seconds=2.0)
    session = Session(
        started=STARTED, target=target, config=cfg, kind=SessionKind.HARD_STOP
    )
    h = Harness(block_on_end=True, duration=2.0)
    h.session = session
    h.runner = SessionRunner(
        session,
        clock=h.clock,
        logger=h.logger,
        scheduler=h.scheduler,
        overlay=h.overlay,
        stop_overlay=h.stop_overlay,
        blur=h.blur,
        app_control=h.app_control,
        workspace_tidy=h.workspace_tidy,
        signals=h.signals,
        url_opener=h.url_opener,
        wifi=h.wifi,
    )
    h.runner.pump()
    h.clock.advance(5.0)
    h.runner.pump()
    assert any("Hard stop" in line for line in h.stop_overlay.shown_lines or [])
