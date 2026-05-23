"""Stable process identity for macOS TCC and detached spawn."""

from __future__ import annotations

import os
import sys
from pathlib import Path

_RUNTIME_PYTHON_ENV = "CTIMELI_RUNTIME_PYTHON"


def runtime_python() -> str:
    """Return the venv ``python`` shim when available.

    macOS privacy (Accessibility, Calendar) is keyed to the exact executable
    path. ``.venv/bin/python`` and ``.venv/bin/python3.14`` resolve to the same
    binary but are separate TCC clients — always run through ``python``.
    """
    exe = Path(sys.executable)
    if exe.parent.name == "bin":
        venv_python = exe.parent / "python"
        if venv_python.is_file():
            return str(venv_python)
    return str(exe)


def ensure_runtime_python() -> None:
    """Re-exec through ``runtime_python()`` once so TCC grants match."""
    if os.environ.get(_RUNTIME_PYTHON_ENV) == "1":
        return
    if "pytest" in sys.modules:
        return

    target = runtime_python()
    if os.path.normpath(sys.executable) == os.path.normpath(target):
        return

    os.environ[_RUNTIME_PYTHON_ENV] = "1"
    os.execv(target, [target, "-m", "ctimeli", *sys.argv[1:]])
