"""Tests for app.session_runner — orchestration via fake adapters."""

import datetime as dt

from countdown import ports
from countdown.app.session_runner import SessionRunner
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
        self.app_control = FakeAppControl(
            frontmost=42,
            running=["Notes"],
            foreground=["Notes", "Finder"],
            names={42: "Notes"},
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


def test_focus_returns_to_prior_app_after_cleanup():
    h = Harness(block_on_end=True, duration=2.0)
    h.runner.pump()
    h.clock.advance(5.0)
    h.runner.pump()  # -> BLOCKING (captures frontmost pid 42 = "Notes")
    h.stop_overlay.dismiss = True
    h.runner.pump()  # -> CLEANUP
    h.runner.pump()  # cleanup runs
    # "Notes" is in the block-end plan, so focus must NOT return to it.
    assert h.app_control.finder_activations == 1
