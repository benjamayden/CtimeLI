"""StdinSource — the InputSource port. See docs/ports.md.

Polls stdin without blocking by setting O_NONBLOCK on the descriptor, and
restores the original flags on close() so the parent shell is not left with a
non-blocking terminal (edge-cases #18).
"""

from __future__ import annotations

import fcntl
import os
import select
import sys


class StdinSource:
    """Non-blocking line reader over stdin."""

    def __init__(self) -> None:
        self._fd = sys.stdin.fileno()
        self._original_flags = fcntl.fcntl(self._fd, fcntl.F_GETFL)
        fcntl.fcntl(self._fd, fcntl.F_SETFL, self._original_flags | os.O_NONBLOCK)
        self._buffer = ""
        self._closed = False

    def poll_lines(self) -> list[str]:
        chunk = self._read_chunk()
        if chunk is None:
            return []
        if chunk == "":  # EOF
            self._closed = True
            return []
        self._buffer += chunk
        lines: list[str] = []
        while "\n" in self._buffer or "\r" in self._buffer:
            line, sep, rest = self._buffer.partition("\n")
            if not sep:
                line, sep, rest = self._buffer.partition("\r")
            self._buffer = rest
            stripped = line.strip()
            if stripped:
                lines.append(stripped)
        return lines

    def closed(self) -> bool:
        return self._closed

    def close(self) -> None:
        fcntl.fcntl(self._fd, fcntl.F_SETFL, self._original_flags)

    def _read_chunk(self) -> str | None:
        try:
            if not select.select([sys.stdin], [], [], 0)[0]:
                return None
            return sys.stdin.read()
        except (BlockingIOError, OSError):
            return None
