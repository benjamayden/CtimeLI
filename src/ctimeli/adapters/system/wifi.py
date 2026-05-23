"""SystemWifi — reads the current Wi-Fi SSID via networksetup."""

from __future__ import annotations

import re
import subprocess
import time

_SSID_RE = re.compile(r"Current Wi-Fi Network:\s*(.+)$", re.MULTILINE)
_INTERFACES = ("en0", "en1")
# SSID only matters at session end — cache to avoid spawning networksetup every frame.
_DEFAULT_REFRESH_SECONDS = 30.0


class SystemWifi:
    """The WifiSource port — subprocess to networksetup, no PyObjC dependency."""

    def __init__(self, *, refresh_seconds: float = _DEFAULT_REFRESH_SECONDS) -> None:
        self._refresh_seconds = refresh_seconds
        self._cached: str | None = None
        self._cached_at: float = 0.0

    def current_ssid(self) -> str | None:
        now = time.monotonic()
        if now - self._cached_at < self._refresh_seconds:
            return self._cached
        self._cached = self._read_ssid()
        self._cached_at = now
        return self._cached

    def _read_ssid(self) -> str | None:
        for iface in _INTERFACES:
            ssid = self._ssid_on_interface(iface)
            if ssid is not None:
                return ssid
        return None

    def _ssid_on_interface(self, iface: str) -> str | None:
        try:
            result = subprocess.run(
                ["networksetup", "-getairportnetwork", iface],
                capture_output=True,
                text=True,
                check=False,
            )
        except OSError:
            return None
        if result.returncode != 0:
            return None
        match = _SSID_RE.search(result.stdout)
        if match is None:
            return None
        ssid = match.group(1).strip()
        if not ssid or ssid.lower() == "you are not associated with an airport network.":
            return None
        return ssid
