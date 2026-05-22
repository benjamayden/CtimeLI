"""Tests for app.session_runner — orchestration via fake adapters."""

import datetime as dt

from countdown import ports
from countdown.app.session_runner import SessionRunner
from countdown.domain.apps import RunningApp
from countdown.domain.config import AppConfig
from countdown.domain.session import Session, SessionKind, SessionState

from .fakes import (
    FakeAppControl,
    FakeBlockExecutor,
    FakeClock,
    FakeOverlay,
    FakeScheduler,
    FakeShaker,
    FakeSignals,
    FakeStopOverlay,
    RecordingLogger,
)

STARTED = dt.datetime(2026, 5, 21, 14, 0, 0)


class Harness:
    """A SessionRunner wired to fakes, with the fakes kept for assertions."""

    def __init__(self, *, block_on_end=False, duration=2.0, shaker_available=True):
        cfg = AppConfig(block_on_end=block_on_end)
        target = STARTED + dt.timedelta(seconds=duration)
        self.session = Session(
            started=STARTED, target=target, config=cfg, kind=SessionKind.MANUAL
        )
        self.clock = FakeClock(STARTED)
        self.logger = RecordingLogger()
        self.scheduler = FakeScheduler()
        self.overlay = FakeOverlay()
        self.stop_overlay = FakeStopOverlay()
        self.shaker = FakeShaker(available=shaker_available)
        _notes = RunningApp(bundle_id="com.apple.Notes", display_name="Notes")
        self.app_control = FakeAppControl(
            frontmost=42,
            running=[_notes],
            foreground=[_notes],
            apps_by_pid={42: _notes},
        )
        self.block_executor = FakeBlockExecutor(counts={"minimize": 2, "hide": 0, "quit": 0})
        self.signals = FakeSignals()
        self.runner = SessionRunner(
            self.session,
            clock=self.clock,
            logger=self.logger,
            scheduler=self.scheduler,
            overlay=self.overlay,
            stop_overlay=self.stop_overlay,
            shaker=self.shaker,
            app_control=self.app_control,
            block_executor=self.block_executor,
            signals=self.signals,
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
    h.runner.pump()  # -> CLEANUP
    assert h.session.state is SessionState.CLEANUP
    assert h.runner.pump() is False  # CLEANUP runs, -> DONE, torn down
    assert h.block_executor.executed is not None
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


def test_shake_is_applied_in_the_wiggle_window():
    # duration 2 s < the 3 s wiggle window -> the very first frame wiggles.
    h = Harness(duration=2.0, shaker_available=True)
    h.runner.pump()
    assert h.shaker.applied  # at least one offset applied


def test_shake_skipped_when_accessibility_unavailable():
    h = Harness(duration=2.0, shaker_available=False)
    h.runner.pump()
    assert h.shaker.applied == []


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
    assert h.block_executor.executed is not None
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


def test_focus_returns_to_prior_app_when_not_in_plan():
    # When the frontmost app is NOT in the block-end plan, focus returns to it.
    h = Harness(block_on_end=True, duration=2.0)
    _safari = RunningApp(bundle_id="com.apple.Safari", display_name="Safari")
    new_ctrl = FakeAppControl(
        frontmost=77, running=[], foreground=[], apps_by_pid={77: _safari}
    )
    h.runner.app_control = new_ctrl
    h.runner.pump()
    h.clock.advance(5.0)
    h.runner.pump()       # -> BLOCKING (captures frontmost pid 77)
    h.stop_overlay.dismiss = True
    h.runner.pump()       # -> CLEANUP
    h.runner.pump()       # cleanup runs -> DONE
    assert new_ctrl.activated_pids == [77]
    assert new_ctrl.finder_activations == 0


def test_focus_returns_to_prior_app_after_cleanup():
    h = Harness(block_on_end=True, duration=2.0)
    h.runner.pump()
    h.clock.advance(5.0)
    h.runner.pump()  # -> BLOCKING (captures frontmost pid 42 = "Notes")
    h.stop_overlay.dismiss = True
    h.runner.pump()  # -> CLEANUP
    h.runner.pump()  # cleanup runs
    # Notes was acted on; Finder is not in the plan → fall back to Finder.
    assert h.app_control.finder_activations == 1


def test_finder_not_reactivated_when_in_plan():
    # If Finder itself was tidied, activate_finder() must not undo that.
    _notes = RunningApp(bundle_id="com.apple.Notes", display_name="Notes")
    _finder = RunningApp(bundle_id="com.apple.finder", display_name="Finder", is_foreground=True)
    h = Harness(block_on_end=True, duration=2.0)
    h.runner.app_control = FakeAppControl(
        frontmost=42,
        running=[_notes],
        foreground=[_notes, _finder],
        apps_by_pid={42: _notes},
    )
    h.runner.pump()
    h.clock.advance(5.0)
    h.runner.pump()  # -> BLOCKING
    h.stop_overlay.dismiss = True
    h.runner.pump()  # -> CLEANUP
    h.runner.pump()  # cleanup runs
    # Finder is in the plan — must not be re-activated.
    assert h.runner.app_control.finder_activations == 0
