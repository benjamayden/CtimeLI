"""WatchInstanceLock — one detached watch child at a time."""

from __future__ import annotations

import fcntl
import os
from pathlib import Path

_LOCK_PATH = Path.home() / ".cache" / "ctimeli" / "watch.lock"


def watch_lock_path() -> Path:
    return _LOCK_PATH


def watch_is_running() -> bool:
    """True when a live process holds the watch lock."""
    try:
        pid = int(_LOCK_PATH.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


class WatchInstanceLock:
    """Non-blocking flock lock; released on teardown."""

    def __init__(self) -> None:
        self._fd: int | None = None

    def try_acquire(self) -> bool:
        _LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(_LOCK_PATH, os.O_CREAT | os.O_RDWR, 0o644)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            os.close(fd)
            return False
        os.ftruncate(fd, 0)
        os.write(fd, str(os.getpid()).encode())
        self._fd = fd
        return True

    def release(self) -> None:
        if self._fd is None:
            return
        fcntl.flock(self._fd, fcntl.LOCK_UN)
        os.close(self._fd)
        self._fd = None
        try:
            _LOCK_PATH.unlink()
        except OSError:
            pass
