"""SystemClock — the real Clock port. See docs/ports.md."""

from __future__ import annotations

import datetime as dt
import time


class SystemClock:
    """Wall-clock and monotonic time from the standard library."""

    def now(self) -> dt.datetime:
        return dt.datetime.now()

    def monotonic(self) -> float:
        return time.monotonic()
