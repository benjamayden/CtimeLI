"""StderrLogger — the real Logger port. See docs/ports.md.

Adapters may print; the domain and app layers must not (they use this port).
"""

from __future__ import annotations

import sys


def _emit(message: str, *, stream) -> None:
    """Print without crashing when stderr/stdout is gone (detached watch child)."""
    try:
        print(message, file=stream, flush=True)
    except BrokenPipeError:
        pass
    except OSError:
        pass


class StderrLogger:
    """info -> stdout; warn / error -> stderr. Always flushed."""

    def info(self, message: str) -> None:
        _emit(message, stream=sys.stdout)

    def warn(self, message: str) -> None:
        _emit(message, stream=sys.stderr)

    def error(self, message: str) -> None:
        _emit(message, stream=sys.stderr)
