"""The session state machine and the RenderFrame it produces.

This is the contract a port must reproduce exactly. See docs/domain.md
section 7 for the transition table. The machine is stateful but pure: every
transition is deterministic given its inputs and the prior state, with no I/O.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from enum import Enum

from .colors import RGB, STROKE_BLUE, stroke_color_for_fraction
from .config import AppConfig
from .curves import pulse_opacity, pulse_spread, shake_intensity
from .math import clamp, format_duration, lerp

# Target render cadence. The runner floors each frame's dt at this value so a
# stalled run loop cannot produce dt == 0 and freeze the smoother (edge-cases #12).
FRAME_INTERVAL = 1.0 / 60.0
# Stroke fraction smoothing rate, per second (see docs/domain.md section 7).
DISPLAY_SMOOTH_RATE = 9.0
# Pulse animation phase advance, per second.
PULSE_PHASE_RATE = 0.85


class SessionKind(Enum):
    """Selects stroke base colour and HUD label format. Open for extension."""

    MANUAL = "manual"
    CALENDAR = "calendar"


class SessionState(Enum):
    """The session lifecycle. See the transition table in docs/domain.md."""

    PENDING = "pending"
    RUNNING = "running"
    BLOCKING = "blocking"
    CLEANUP = "cleanup"
    DONE = "done"
    INTERRUPTED = "interrupted"


_TERMINAL = frozenset({SessionState.DONE, SessionState.INTERRUPTED})


@dataclass(frozen=True)
class RenderFrame:
    """The entire UI contract: what the overlay draws for one frame.

    Plain data — the overlay renders this and asks the domain nothing. A new
    visual is a new field here, computed in Session.tick.
    """

    fraction: float
    label: str
    color: RGB
    pulse_opacity: float
    pulse_spread: float
    pulse_phase: float
    shake: float


class Session:
    """One countdown's state machine and per-frame render computation."""

    def __init__(
        self,
        *,
        started: dt.datetime,
        target: dt.datetime,
        config: AppConfig,
        kind: SessionKind = SessionKind.MANUAL,
        event_start: dt.datetime | None = None,
        event_id: str | None = None,
        event_title: str | None = None,
    ) -> None:
        self.config = config
        self.started = started
        self.target = target
        self.kind = kind
        self.event_start = event_start
        self.event_id = event_id
        self.event_title = event_title
        self.total_seconds = max(1.0, (target - started).total_seconds())
        self.state = SessionState.PENDING
        # True if Ctrl+C / stop() fired — used for the exit message even when
        # the machine still routes through CLEANUP (see docs/domain.md section 7).
        self.interrupted = False
        # True once the session has entered the block-on-end path.
        self.blocked = False
        self._display_fraction = 1.0
        self._pulse_phase = 0.0

    # -- queries -------------------------------------------------------------

    @property
    def is_terminal(self) -> bool:
        return self.state in _TERMINAL

    @property
    def base_color(self) -> RGB:
        """Stroke base colour for this session kind."""
        if self.kind is SessionKind.CALENDAR:
            return RGB(
                self.config.calendar_stroke_r,
                self.config.calendar_stroke_g,
                self.config.calendar_stroke_b,
            )
        return STROKE_BLUE

    # -- transitions ---------------------------------------------------------

    def start(self) -> None:
        """PENDING -> RUNNING."""
        if self.state is SessionState.PENDING:
            self.state = SessionState.RUNNING

    def tick(self, now: dt.datetime, dt_seconds: float) -> RenderFrame:
        """Advance one frame. Precondition: state is RUNNING.

        Transitions to BLOCKING or DONE when the target is reached. Returns the
        RenderFrame for this instant regardless.
        """
        remaining = max(0.0, (self.target - now).total_seconds())
        target_fraction = clamp(remaining / self.total_seconds, 0.0, 1.0)
        self._display_fraction = lerp(
            self._display_fraction, target_fraction, dt_seconds, DISPLAY_SMOOTH_RATE
        )
        self._pulse_phase += dt_seconds * PULSE_PHASE_RATE
        frame = RenderFrame(
            fraction=self._display_fraction,
            label=self._label(remaining),
            color=stroke_color_for_fraction(
                self._display_fraction, self.config.red_zone_fraction, self.base_color
            ),
            pulse_opacity=pulse_opacity(remaining, self.config),
            pulse_spread=pulse_spread(remaining, self.config),
            pulse_phase=self._pulse_phase,
            shake=shake_intensity(remaining, self.config),
        )
        if remaining <= 0.0:
            self._end()
        return frame

    def finish(self) -> None:
        """Finish early (HUD button). RUNNING -> BLOCKING or DONE."""
        if self.state is SessionState.RUNNING:
            self._end()

    def retarget(
        self,
        new_target: dt.datetime,
        now: dt.datetime,
        *,
        kind: SessionKind | None = None,
        event_start: dt.datetime | None = None,
        event_id: str | None = None,
        event_title: str | None = None,
    ) -> bool:
        """Move the live target (calendar snap). Returns True if applied.

        Invariant: total_seconds only ever grows — pulling the target in must
        not make the ring jump backwards (see docs/domain.md "Retarget").
        """
        if self.state is not SessionState.RUNNING or new_target <= now:
            return False
        self.target = new_target
        self.total_seconds = max(
            self.total_seconds, (new_target - self.started).total_seconds()
        )
        if kind is not None:
            self.kind = kind
        if event_start is not None:
            self.event_start = event_start
        if event_id is not None:
            self.event_id = event_id
        if event_title is not None:
            self.event_title = event_title
        return True

    def interrupt(self) -> None:
        """Ctrl+C / stop(). Latches the interrupted flag and routes to exit.

        From BLOCKING this routes through CLEANUP so windows are still tidied
        (see docs/domain.md section 7); from RUNNING/PENDING it ends directly.
        """
        if self.is_terminal:
            return
        self.interrupted = True
        if self.state is SessionState.BLOCKING:
            self.state = SessionState.CLEANUP
        elif self.state is not SessionState.CLEANUP:
            self.state = SessionState.INTERRUPTED

    def dismiss(self) -> None:
        """Stop overlay dismissed. BLOCKING -> CLEANUP."""
        if self.state is SessionState.BLOCKING:
            self.state = SessionState.CLEANUP

    def cleaned(self) -> None:
        """Block-end actions applied. CLEANUP -> DONE."""
        if self.state is SessionState.CLEANUP:
            self.state = SessionState.DONE

    # -- internals -----------------------------------------------------------

    def _end(self) -> None:
        """Shared RUNNING-exit decision for both zero and finish()."""
        if self.config.block_on_end:
            self.blocked = True
            self.state = SessionState.BLOCKING
        else:
            self.state = SessionState.DONE

    def _label(self, remaining: float) -> str:
        text = format_duration(remaining)
        if self.kind is SessionKind.CALENDAR and self.event_start is not None:
            text = f"{text} · {self.event_start.strftime('%H:%M')}"
        return text
