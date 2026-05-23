"""SigintListener — the SignalListener port. See docs/ports.md.

The handler only latches a flag; the app polls it between frames. Doing real
work inside a signal handler is a re-entrancy bug (edge-cases #20).
"""

from __future__ import annotations

import signal
from typing import Any


class SigintListener:
    """Latches SIGINT (Ctrl+C) into a polled boolean."""

    def __init__(self) -> None:
        self._interrupted = False
        self._previous: Any = None

    def install(self) -> None:
        self._previous = signal.signal(signal.SIGINT, self._handle)

    def interrupted(self) -> bool:
        return self._interrupted

    def clear(self) -> None:
        """Reset after a session consumed SIGINT (watch must stay alive)."""
        self._interrupted = False

    def restore(self) -> None:
        if self._previous is not None:
            signal.signal(signal.SIGINT, self._previous)
            self._previous = None

    def _handle(self, _signum: int, _frame: object) -> None:
        self._interrupted = True
