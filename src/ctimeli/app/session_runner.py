"""SessionRunner — drives one countdown session.

Owns the frame loop: pull time from the Clock, ask the domain Session what to
render, push it to the overlay, react to finish / interrupt / block-end. It is
written entirely against ports, so tests drive it with fakes.
"""

from __future__ import annotations

import datetime as dt

from ctimeli import ports
from ctimeli.domain.apps import AppSelector, RunningApp, app_matches_selector
from ctimeli.domain.calendar import is_work_wifi
from ctimeli.domain.math import sleep_gap_seconds
from ctimeli.domain.session import FRAME_INTERVAL, Session, SessionKind, SessionState
from ctimeli.terminal_ui import ok, warn

_SLEEP_GAP_THRESHOLD = 2.0

_DISMISS_HINT = "Click anywhere to tidy windows · Return · or Ctrl+C"
_DEFAULT_STOP_LINES = [
    "It's time to stop.",
    "Your session has ended.",
    _DISMISS_HINT,
]


def _stop_lines(session: Session) -> list[str]:
    if session.kind is SessionKind.HARD_STOP:
        return [
            "End of day.",
            "Hard stop — time to wrap up.",
            _DISMISS_HINT,
        ]
    if session.kind is SessionKind.CALENDAR and session.room:
        return [
            "It's time to go.",
            f"Room: {session.room}",
            _DISMISS_HINT,
        ]
    return list(_DEFAULT_STOP_LINES)


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
        blur: ports.ScreenBlur,
        app_control: ports.AppControl,
        workspace_tidy: ports.WorkspaceTidy,
        signals: ports.SignalListener,
        url_opener: ports.UrlOpener,
        wifi: ports.WifiSource,
        extra_skip: frozenset[AppSelector] = frozenset(),
    ) -> None:
        self.session = session
        self.clock = clock
        self.logger = logger
        self.scheduler = scheduler
        self.overlay = overlay
        self.stop_overlay = stop_overlay
        self.blur = blur
        self.app_control = app_control
        self.workspace_tidy = workspace_tidy
        self.signals = signals
        self.url_opener = url_opener
        self.wifi = wifi
        # Apps the block-end tidy must leave alone (the host terminal in watch).
        self.extra_skip = extra_skip
        self._setup_done = False
        self._torn_down = False
        self._blocking_ui_shown = False
        self._interrupt_seen = False
        self._last_tick: dt.datetime | None = None
        self._last_mono: float | None = None
        self._restore_focus_pid: int | None = None
        self._call_link_opened = False
        self._yield_loop = True

    def run(self) -> Session:
        """Blocking one-shot loop. Returns the session in its terminal state."""
        while self.pump():
            pass
        return self.session

    def pump(self, *, yield_loop: bool = True) -> bool:
        """Advance one frame. Returns False once terminal and torn down."""
        self._yield_loop = yield_loop
        if self._torn_down:
            return False
        if not self._setup_done:
            self._setup()

        now = self.clock.now()
        mono = self.clock.monotonic()

        if self.signals.interrupted() and not self._interrupt_seen:
            self._interrupt_seen = True
            self.session.interrupt()

        state = self.session.state
        if state is SessionState.RUNNING:
            if self._sleep_gap_seconds(now, mono) > 0.0:
                self.session.abandon_for_sleep()
                self._maybe_open_call_link()
            else:
                dt_seconds = self._frame_dt(now, mono)
                self._run_frame(now, dt_seconds)

        if self.session.state is SessionState.BLOCKING:
            self._ensure_blocking_ui()
            if self.stop_overlay.dismissed():
                self.session.dismiss()

        if self.session.state is SessionState.CLEANUP:
            self._run_cleanup()
            self.session.cleaned()

        if self.session.is_terminal:
            self._teardown()
            return False
        if yield_loop:
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
        self.overlay.show()
        self.blur.show()
        self._last_tick = self.clock.now()
        self._last_mono = self.clock.monotonic()

    def _sleep_gap_seconds(self, now: dt.datetime, mono: float) -> float:
        if self._last_tick is None or self._last_mono is None:
            return 0.0
        wall_delta = (now - self._last_tick).total_seconds()
        mono_delta = mono - self._last_mono
        return sleep_gap_seconds(
            wall_delta, mono_delta, threshold=_SLEEP_GAP_THRESHOLD
        )

    def _frame_dt(self, now: dt.datetime, mono: float) -> float:
        """Monotonic seconds since the last tick, floored at FRAME_INTERVAL.

        Monotonic time pauses during system sleep, so smoothers do not burst on
        wake. The floor stops a stalled run loop from yielding dt == 0 (edge-cases #12).
        """
        if self._last_tick is None or self._last_mono is None:
            self._last_tick = now
            self._last_mono = mono
            return FRAME_INTERVAL
        dt_seconds = max(FRAME_INTERVAL, mono - self._last_mono)
        self._last_tick = now
        self._last_mono = mono
        return dt_seconds

    def _on_work_wifi(self) -> bool:
        return is_work_wifi(
            self.wifi.current_ssid(), self.session.config.work_wifi_ssids
        )

    def _run_frame(self, now: dt.datetime, dt_seconds: float) -> None:
        remaining = max(0.0, (self.session.target - now).total_seconds())
        # Work-Wi-Fi only affects the zero/finish decision — not every frame.
        need_wifi = self.overlay.finish_requested() or remaining <= dt_seconds
        on_work = self._on_work_wifi() if need_wifi else False
        if self.overlay.finish_requested():
            self.session.finish(on_work_wifi=on_work)
        else:
            frame = self.session.tick(now, dt_seconds, on_work_wifi=on_work)
            if self.session.state is SessionState.RUNNING:
                self.overlay.render(frame)
                self.blur.set_intensity(frame.blur)
        if self.session.state is SessionState.DONE:
            self._maybe_open_call_link()

    def _ensure_blocking_ui(self) -> None:
        if self._blocking_ui_shown:
            return
        self._blocking_ui_shown = True
        self._restore_focus_pid = self.app_control.frontmost_pid()
        self.overlay.hide()
        self.blur.set_intensity(1.0)
        self.app_control.set_activation_policy(ports.ActivationPolicy.REGULAR)
        self.stop_overlay.show(_stop_lines(self.session))

    def _maybe_open_call_link(self) -> None:
        session = self.session
        if self._call_link_opened:
            return
        if not (
            session.kind is SessionKind.CALENDAR
            and session.call_url
            and not session.room
        ):
            return
        if is_work_wifi(self.wifi.current_ssid(), session.config.work_wifi_ssids):
            return
        self._call_link_opened = True
        if self.url_opener.open(session.call_url):
            self.logger.info(ok("Call link opened in browser."))
        else:
            self.logger.warn(warn("Could not open call link."))

    def _run_cleanup(self) -> None:
        close = self._yield_loop
        self.stop_overlay.hide(close=close)
        self.blur.hide()
        self.overlay.hide()
        if self._yield_loop:
            self.scheduler.pump(0.05)
        if self._yield_loop:
            self.app_control.set_activation_policy(ports.ActivationPolicy.PROHIBITED)
        else:
            self.app_control.set_activation_policy(ports.ActivationPolicy.ACCESSORY)
        if self._restore_focus_pid is not None:
            self.app_control.activate_pid(self._restore_focus_pid)
        if self._yield_loop:
            self.scheduler.pump(0.05)
        self.workspace_tidy.tidy_focused(skip=self.extra_skip, pump=self._yield_loop)
        self.logger.info(ok("Block end — hid other apps, minimized window."))
        self._restore_focus()

    def _restore_focus(self) -> None:
        """If the pre-block app is a skip app, re-activate it after the tidy."""
        pid = self._restore_focus_pid
        if pid is None:
            return
        app = self.app_control.app_for_pid(pid)
        if app is not None and any(app_matches_selector(app, sel) for sel in self.extra_skip):
            self.app_control.activate_pid(pid)

    def _teardown(self) -> None:
        if self._torn_down:
            return
        self._torn_down = True
        close = self._yield_loop
        self.stop_overlay.hide(close=close)
        if self._yield_loop:
            self.blur.teardown(close=True)
            self.overlay.teardown(close=True)
            self.scheduler.stop()
            return
        # Watch: defer order-out teardown — window.close() segfaults under AppHelper (#46).
        blur, overlay = self.blur, self.overlay

        def _destroy_ui() -> None:
            blur.teardown(close=False)
            overlay.teardown(close=False)

        from PyObjCTools import AppHelper

        AppHelper.callLater(0, _destroy_ui)
