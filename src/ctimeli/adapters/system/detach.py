"""spawn_detached_watch — launch watch mode in a background subprocess."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

WATCH_CHILD_ENV = "CTIMELI_WATCH_CHILD"
WATCH_FOREGROUND_ENV = "CTIMELI_WATCH_FOREGROUND"
_STATUS = "CtimeLI watch running (menu bar icon). You can close this terminal."
_LOG_PATH = Path.home() / ".cache" / "ctimeli" / "watch.log"


def watch_log_path() -> Path:
    return _LOG_PATH


def spawn_detached_watch(watch_argv: list[str]) -> None:
    """Start watch in a new session and return immediately.

    Uses subprocess rather than ``os.fork()`` because fork after PyObjC/AppKit
    initialization aborts on macOS (edge-cases #37).
    """
    from ctimeli.adapters.system.watch_lock import watch_is_running

    if watch_is_running():
        print("CtimeLI watch is already running (menu bar).", flush=True)
        print(f"Log: {_LOG_PATH}", flush=True)
        return

    env = os.environ.copy()
    env[WATCH_CHILD_ENV] = "1"
    cmd = [sys.executable, "-m", "ctimeli", "watch", *watch_argv]

    _LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _LOG_PATH.open("a", encoding="utf-8") as log:
        log.write(f"\n--- spawn {cmd} cwd={os.getcwd()} ---\n")

    log_fd = os.open(_LOG_PATH, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
    try:
        subprocess.Popen(
            cmd,
            stdin=subprocess.DEVNULL,
            stdout=log_fd,
            stderr=log_fd,
            start_new_session=True,
            env=env,
            cwd=os.getcwd(),
            close_fds=True,
        )
    finally:
        os.close(log_fd)

    print(_STATUS, flush=True)
    print(f"Log: {_LOG_PATH}", flush=True)
