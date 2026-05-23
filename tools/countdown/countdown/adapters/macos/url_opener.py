"""MacUrlOpener — opens URLs in the default browser via NSWorkspace."""

from __future__ import annotations

import AppKit
from Foundation import NSURL


class MacUrlOpener:
    """The UrlOpener port — delegates to the system default browser."""

    def open(self, url: str) -> bool:
        ns_url = NSURL.URLWithString_(url)
        if ns_url is None:
            return False
        return bool(AppKit.NSWorkspace.sharedWorkspace().openURL_(ns_url))
