"""Fake adapters for the application-layer tests (docs/development.md tier 2).

Each fake honours its port's contract (docs/ports.md) and records what it was
asked to do, so a test can assert on behaviour with no Mac and no display.
"""

from __future__ import annotations

import datetime as dt

from countdown import ports
from countdown.domain.apps import RunningApp
from countdown.domain.blockend import BlockAction
from countdown.domain.calendar import CalendarEvent
from countdown.domain.session import RenderFrame


class FakeClock:
    """Manually advanced Clock."""

    def __init__(self, start: dt.datetime, monotonic: float = 0.0) -> None:
        self._now = start
        self._mono = monotonic

    def now(self) -> dt.datetime:
        return self._now

    def monotonic(self) -> float:
        return self._mono

    def advance(self, seconds: float) -> None:
        self._now += dt.timedelta(seconds=seconds)
        self._mono += seconds


class RecordingLogger:
    """Logger that keeps every message for assertions."""

    def __init__(self) -> None:
        self.info_lines: list[str] = []
        self.warn_lines: list[str] = []
        self.error_lines: list[str] = []

    def info(self, message: str) -> None:
        self.info_lines.append(message)

    def warn(self, message: str) -> None:
        self.warn_lines.append(message)

    def error(self, message: str) -> None:
        self.error_lines.append(message)

    @property
    def all_lines(self) -> list[str]:
        return self.info_lines + self.warn_lines + self.error_lines


class FakeScheduler:
    """FrameScheduler whose pump does nothing."""

    def __init__(self) -> None:
        self.pump_calls = 0
        self.stopped = False

    def pump(self, seconds: float) -> None:
        self.pump_calls += 1

    def stop(self) -> None:
        self.stopped = True


class FakeOverlay:
    """CountdownOverlay that records every frame and lifecycle call."""

    def __init__(self) -> None:
        self.frames: list[RenderFrame] = []
        self.shown = False
        self.hidden = False
        self.torn_down = False
        self.finish = False

    def show(self) -> None:
        self.shown = True

    def render(self, frame: RenderFrame) -> None:
        self.frames.append(frame)

    def finish_requested(self) -> bool:
        return self.finish

    def hide(self) -> None:
        self.hidden = True

    def teardown(self) -> None:
        self.torn_down = True


class FakeStopOverlay:
    """StopOverlay with a test-controlled dismissed flag."""

    def __init__(self) -> None:
        self.shown_lines: list[str] | None = None
        self.hidden = False
        self.dismiss = False

    def show(self, lines: list[str]) -> None:
        self.shown_lines = lines

    def dismissed(self) -> bool:
        return self.dismiss

    def hide(self) -> None:
        self.hidden = True


class FakeShaker:
    """WindowShaker that records offsets."""

    def __init__(self, available: bool = True) -> None:
        self._available = available
        self.applied: list[tuple[float, float]] = []
        self.restores = 0

    def available(self) -> bool:
        return self._available

    def apply(self, dx: float, dy: float) -> bool:
        self.applied.append((dx, dy))
        return self._available

    def restore(self) -> None:
        self.restores += 1


class FakeAppControl:
    """AppControl with scripted lists and recorded calls."""

    def __init__(
        self,
        *,
        frontmost: int | None = None,
        running: list[RunningApp] | None = None,
        foreground: list[RunningApp] | None = None,
        apps_by_pid: dict[int, RunningApp] | None = None,
    ) -> None:
        self._frontmost = frontmost
        self._running = running or []
        self._foreground = foreground or []
        self._apps_by_pid = apps_by_pid or {}
        self.activated_pids: list[int] = []
        self.finder_activations = 0
        self.policies: list[ports.ActivationPolicy] = []

    def frontmost_pid(self) -> int | None:
        return self._frontmost

    def app_for_pid(self, pid: int) -> RunningApp | None:
        return self._apps_by_pid.get(pid)

    def activate_pid(self, pid: int) -> bool:
        self.activated_pids.append(pid)
        return pid in self._apps_by_pid

    def activate_finder(self) -> None:
        self.finder_activations += 1

    def running_apps(self) -> list[RunningApp]:
        return list(self._running)

    def foreground_apps(self) -> list[RunningApp]:
        return list(self._foreground)

    def set_activation_policy(self, policy: ports.ActivationPolicy) -> None:
        self.policies.append(policy)


class FakeBlockExecutor:
    """BlockEndExecutor that records the plan and returns scripted counts."""

    def __init__(self, counts: dict[str, int] | None = None) -> None:
        self.executed: list[tuple[str, BlockAction]] | None = None
        self._counts = counts or {"minimize": 0, "hide": 0, "quit": 0}

    def execute(self, plan: list[tuple[str, BlockAction]]) -> dict[str, int]:
        self.executed = list(plan)
        return self._counts


class FakeCalendar:
    """CalendarSource returning a scripted event."""

    def __init__(self, event: CalendarEvent | None = None, access: bool = True) -> None:
        self.event = event
        self._access = access
        self.access_calls = 0

    def ensure_access(self) -> bool:
        self.access_calls += 1
        return self._access

    def nearest_event_within(self, minutes: float) -> CalendarEvent | None:
        return self.event


class FakeInput:
    """InputSource fed by a queue of line batches."""

    def __init__(self) -> None:
        self._batches: list[list[str]] = []
        self._closed = False
        self.close_calls = 0

    def feed(self, *lines: str) -> None:
        """Queue one batch of lines for the next poll_lines() call."""
        self._batches.append(list(lines))

    def poll_lines(self) -> list[str]:
        return self._batches.pop(0) if self._batches else []

    def closed(self) -> bool:
        return self._closed

    def set_closed(self) -> None:
        self._closed = True

    def close(self) -> None:
        self.close_calls += 1


class FakeSignals:
    """SignalListener with a test-controlled interrupted flag."""

    def __init__(self) -> None:
        self._interrupted = False
        self.installed = False
        self.restored = False

    def install(self) -> None:
        self.installed = True

    def interrupted(self) -> bool:
        return self._interrupted

    def restore(self) -> None:
        self.restored = True

    def trigger(self) -> None:
        self._interrupted = True


class FakeUrlOpener:
    """UrlOpener that records opened URLs."""

    def __init__(self, *, succeed: bool = True) -> None:
        self.opened: list[str] = []
        self._succeed = succeed

    def open(self, url: str) -> bool:
        if self._succeed:
            self.opened.append(url)
            return True
        return False


class FakeWifiSource:
    """WifiSource with a test-controlled SSID."""

    def __init__(self, ssid: str | None = None) -> None:
        self.ssid = ssid

    def current_ssid(self) -> str | None:
        return self.ssid
