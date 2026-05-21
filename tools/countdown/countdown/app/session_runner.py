"""SessionRunner — drives one countdown session.

Owns the frame loop: pull time from the Clock, ask the domain Session what to
render, push it to the overlay, react to finish / interrupt / block-end. It is
written entirely against ports, so tests drive it with fakes.
"""

from __future__ import annotations

import datetime as dt

from countdown import ports
from countdown.domain.blockend import block_end_summary, plan_block_end
from countdown.domain.session import FRAME_INTERVAL, Session, SessionState
from countdown.domain.shake import ShakeMotion

_STOP_LINES = [
    "It's time to stop.",
    "Your session has ended.",
    "Click anywhere to tidy windows · Return · or Ctrl+C",
]


class SessionRunner:
    """Runs a single Session to a terminal state."""

    def __init__(
        self,
        session: Session,
        *,
        clock: ports.Clock,
        logger: ports.Logger,
        scheduler: ports.FrameScheduler,
        overlay: ports.CountdownOverlay,
        stop_overlay: ports.StopOverlay,
        shaker: ports.WindowShaker,
        app_control: ports.AppControl,
        block_executor: ports.BlockEndExecutor,
        signals: ports.SignalListener,
        extra_skip: frozenset[str] = frozenset(),
    ) -> None:
        self.session = session
        self.clock = clock
        self.logger = logger
        self.scheduler = scheduler
        self.overlay = overlay
        self.stop_overlay = stop_overlay
        self.shaker = shaker
        self.app_control = app_control
        self.block_executor = block_executor
        self.signals = signals
        # Apps the block-end tidy must leave alone (the host terminal in watch).
        self.extra_skip = extra_skip
        self._motion = ShakeMotion(session.config)
        self._setup_done = False
        self._torn_down = False
        self._interrupt_seen = False
        self._last_tick: dt.datetime | None = None
        self._restore_focus_pid: int | None = None

    def run(self) -> Session:
        """Blocking one-shot loop. Returns the session in its terminal state."""
        while self.pump():
            pass
        return self.session

    def pump(self) -> bool:
        """Advance one frame. Returns False once terminal and torn down."""
        if self._torn_down:
            return False
        if not self._setup_done:
            self._setup()

        now = self.clock.now()
        dt_seconds = self._frame_dt(now)

        if self.signals.interrupted() and not self._interrupt_seen:
            self._interrupt_seen = True
            self.session.interrupt()

        state = self.session.state
        if state is SessionState.RUNNING:
            self._run_frame(now, dt_seconds)
        elif state is SessionState.BLOCKING:
            if self.stop_overlay.dismissed():
                self.session.dismiss()
        elif state is SessionState.CLEANUP:
            self._run_cleanup()
            self.session.cleaned()

        if self.session.is_terminal:
            self._teardown()
            return False
        self.scheduler.pump(FRAME_INTERVAL)
        return True

    def stop(self) -> None:
        """Abandon the session immediately (used when watch mode replaces it)."""
        self.session.interrupt()
        self._teardown()

    # -- internals -----------------------------------------------------------

    def _setup(self) -> None:
        self._setup_done = True
        self.session.start()
        self.app_control.set_activation_policy(ports.ActivationPolicy.ACCESSORY)
        self.overlay.set_base_color(self.session.base_color)
        self.overlay.show()
        self._last_tick = self.clock.now()

    def _frame_dt(self, now: dt.datetime) -> float:
        """Wall-clock seconds since the last tick, floored at FRAME_INTERVAL.

        The floor stops a stalled run loop from yielding dt == 0, which would
        freeze every lerp-based smoother (edge-cases #12).
        """
        if self._last_tick is None:
            self._last_tick = now
        dt_seconds = max(FRAME_INTERVAL, (now - self._last_tick).total_seconds())
        self._last_tick = now
        return dt_seconds

    def _run_frame(self, now: dt.datetime, dt_seconds: float) -> None:
        if self.overlay.finish_requested():
            self.session.finish()
        else:
            frame = self.session.tick(now, dt_seconds)
            if self.session.state is SessionState.RUNNING:
                self.overlay.render(frame)
                self._apply_shake(frame.shake, dt_seconds)
        if self.session.state is SessionState.BLOCKING:
            self._enter_blocking()

    def _apply_shake(self, intensity: float, dt_seconds: float) -> None:
        if intensity <= 0.0 or not self.shaker.available():
            self._motion.reset()
            self.shaker.restore()
            return
        dx, dy = self._motion.offset(intensity, dt_seconds)
        self.shaker.apply(dx, dy)

    def _enter_blocking(self) -> None:
        self._restore_focus_pid = self.app_control.frontmost_pid()
        self.shaker.restore()
        self.overlay.hide()
        self.app_control.set_activation_policy(ports.ActivationPolicy.REGULAR)
        self.stop_overlay.show(list(_STOP_LINES))

    def _run_cleanup(self) -> None:
        self.stop_overlay.hide()
        self.overlay.hide()
        plan = plan_block_end(
            self.app_control.running_app_names(),
            self.app_control.foreground_app_names(),
            self.session.config,
            self.extra_skip,
        )
        counts = self.block_executor.execute(plan)
        summary = block_end_summary(counts)
        if summary:
            self.logger.info(summary)
        self._restore_focus({name for name, _ in plan})

    def _restore_focus(self, acted_names: set[str]) -> None:
        """Return focus to where it was — unless that app was just tidied."""
        pid = self._restore_focus_pid
        if pid is not None:
            name = self.app_control.app_name_for_pid(pid)
            if name and name not in acted_names and self.app_control.activate_pid(pid):
                return
        self.app_control.activate_finder()

    def _teardown(self) -> None:
        if self._torn_down:
            return
        self._torn_down = True
        self.shaker.restore()
        self.overlay.teardown()
        self.stop_overlay.hide()
        self.scheduler.stop()
