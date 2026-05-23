"""StderrLogger — the real Logger port. See docs/ports.md.

Adapters may print; the domain and app layers must not (they use this port).
"""

from __future__ import annotations

import sys


class StderrLogger:
    """info -> stdout; warn / error -> stderr. Always flushed."""

    def info(self, message: str) -> None:
        print(message, flush=True)

    def warn(self, message: str) -> None:
        print(message, file=sys.stderr, flush=True)

    def error(self, message: str) -> None:
        print(message, file=sys.stderr, flush=True)
