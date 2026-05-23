"""Ports — the interfaces the application depends on.

Every Port is a structural Protocol. The application and domain are written
against these; adapters (countdown/adapters/) implement them; tests use fakes.
Contracts, pre/post-conditions and failure modes are in docs/ports.md.

Port signatures use only stdlib and domain types — never a platform type.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Mapping
from enum import Enum
from typing import Protocol, runtime_checkable

from .domain.apps import AppSelector, RunningApp
from .domain.calendar import CalendarEvent
from .domain.session import RenderFrame


class ActivationPolicy(Enum):
    """How the process presents itself while a session runs."""

    ACCESSORY = "accessory"  # no Dock icon — during a countdown
    PROHIBITED = "prohibited"  # fully hidden — watcher idle
    REGULAR = "regular"  # focusable — for the stop overlay


@runtime_checkable
class Clock(Protocol):
    """Time source. Keeps the domain and app off any real clock."""

    def now(self) -> dt.datetime:
        """Current wall-clock local time."""

    def monotonic(self) -> float:
        """Seconds from an arbitrary epoch; never decreasing."""


@runtime_checkable
class Logger(Protocol):
    """All user-facing text. Replaces scattered print() calls."""

    def info(self, message: str) -> None: ...
    def warn(self, message: str) -> None: ...
    def error(self, message: str) -> None: ...


@runtime_checkable
class FrameScheduler(Protocol):
    """Yields to the host UI event loop so overlays repaint.

    The runner owns the frame loop and drives ticks itself; this port only
    drains pending platform UI events between ticks.
    """

    def pump(self, seconds: float) -> None:
        """Process pending UI events for up to `seconds`."""

    def stop(self) -> None:
        """Release any run-loop resources. Idempotent."""


@runtime_checkable
class CountdownOverlay(Protocol):
    """Renders the stroke + edge glow + HUD on every display."""

    def show(self) -> None:
        """Create one click-through overlay window per display."""

    def render(self, frame: RenderFrame) -> None:
        """Draw `frame` on every display.

        `frame.color` is the final stroke colour (red-zone blend and any
        calendar recolour already applied) — the overlay never computes colour.
        """

    def finish_requested(self) -> bool:
        """True once the user clicked the HUD Finish button (latched)."""

    def hide(self) -> None:
        """Order the windows out (while the stop overlay is up)."""

    def teardown(self) -> None:
        """Close and release everything. Idempotent."""


@runtime_checkable
class StopOverlay(Protocol):
    """The full-screen block-on-end modal."""

    def show(self, lines: list[str]) -> None:
        """Cover every display with an opaque modal showing `lines`."""

    def dismissed(self) -> bool:
        """True once dismissed AND the input lockout has elapsed."""

    def hide(self) -> None:
        """Remove the modal. Idempotent."""


@runtime_checkable
class ScreenBlur(Protocol):
    """Progressive full-screen blur above the stroke/glow, below the block modal."""

    def show(self) -> None:
        """Create one click-through blur window per display."""

    def set_intensity(self, amount: float) -> None:
        """Set blur strength 0..1 on every display."""

    def hide(self) -> None:
        """Order blur windows out. Idempotent."""

    def teardown(self) -> None:
        """Close and release everything. Idempotent."""


@runtime_checkable
class AppControl(Protocol):
    """Query and steer running applications (focus, listing, activation)."""

    def frontmost_pid(self) -> int | None:
        """Frontmost app PID; None if it is our own process."""

    def app_for_pid(self, pid: int) -> RunningApp | None:
        """RunningApp for a PID; None if not found."""

    def activate_pid(self, pid: int) -> bool:
        """Bring an app to the front; False if it is gone."""

    def activate_finder(self) -> None:
        """Fallback focus target after a tidy."""

    def running_apps(self) -> list[RunningApp]:
        """Every regular GUI app, including windowless ones."""

    def foreground_apps(self) -> list[RunningApp]:
        """Apps with a visible foreground presence (background only = false)."""

    def set_activation_policy(self, policy: ActivationPolicy) -> None: ...


@runtime_checkable
class WorkspaceTidy(Protocol):
    """Hides other apps and minimizes the focused window after block-on-end."""

    def tidy_focused(self, *, skip: frozenset[AppSelector]) -> None:
        """Option+Cmd+H hide others, then Cmd+M minimize front unless skipped."""


@runtime_checkable
class CalendarSource(Protocol):
    """Supplies the nearest upcoming accepted event."""

    def ensure_access(self) -> bool:
        """Acquire read permission. Idempotent; caches the result."""

    def nearest_event_within(self, minutes: float) -> CalendarEvent | None:
        """Nearest accepted event starting in (now, now+minutes], or None."""


@runtime_checkable
class InputSource(Protocol):
    """Non-blocking line input for watch mode."""

    def poll_lines(self) -> list[str]:
        """Complete lines typed since the last call. Never blocks."""

    def closed(self) -> bool:
        """True once stdin reaches EOF."""

    def close(self) -> None:
        """Restore the terminal to blocking mode. Must run on shutdown."""


@runtime_checkable
class SignalListener(Protocol):
    """Surfaces Ctrl+C as a polled flag, not an exception."""

    def install(self) -> None: ...

    def interrupted(self) -> bool:
        """True once SIGINT has fired (latched)."""

    def restore(self) -> None: ...


@runtime_checkable
class UrlOpener(Protocol):
    """Opens a URL in the system default browser."""

    def open(self, url: str) -> bool:
        """Return True if the URL was handed to the workspace."""


@runtime_checkable
class WifiSource(Protocol):
    """Reports the current Wi-Fi network name."""

    def current_ssid(self) -> str | None:
        """Connected SSID, or None if unavailable or not on Wi-Fi."""


@runtime_checkable
class EnvSource(Protocol):
    """Configuration values, read without mutating os.environ."""

    def values(self) -> Mapping[str, str]:
        """Process environment merged over .env-file values."""
