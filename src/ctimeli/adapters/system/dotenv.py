"""DotEnvSource — the EnvSource port.

Reads a .env file into a mapping and merges the process environment over it.
It never writes to os.environ (edge-cases #5). See docs/ports.md.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path


class DotEnvSource:
    """Configuration values: process environment over .env-file values."""

    def __init__(self, env_path: Path) -> None:
        self._env_path = env_path

    def values(self) -> Mapping[str, str]:
        merged: dict[str, str] = dict(self._load_file())
        merged.update(os.environ)  # process environment wins over the file
        return merged

    def _load_file(self) -> dict[str, str]:
        if not self._env_path.is_file():
            return {}
        parsed: dict[str, str] = {}
        for line in self._env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key:
                parsed[key] = value
        return parsed
