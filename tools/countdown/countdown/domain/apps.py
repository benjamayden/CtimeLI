"""App identity types and name-matching helpers. See docs/domain.md.

RunningApp and AppSelector are the domain's view of a running process.
The alias table and matching logic live here so blockend.py never duplicates them.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

# Restricted charset — alphanumeric, dots, hyphens only. No injection characters.
_BUNDLE_ID_RE = re.compile(r"^[A-Za-z0-9.\-]+$")

# Casual .env names → the System Events / NSWorkspace process names.
_PROCESS_ALIASES: dict[str, frozenset[str]] = {
    "chrome": frozenset({"Google Chrome", "Chrome"}),
    "google chrome": frozenset({"Google Chrome", "Chrome"}),
    "settings": frozenset({"System Settings", "Settings"}),
    "system preferences": frozenset({"System Settings"}),
    "iterm": frozenset({"iTerm2", "iTerm"}),
    "vscode": frozenset({"Code"}),
    "terminal": frozenset({"Terminal", "Apple_Terminal"}),
    "apple_terminal": frozenset({"Terminal", "Apple_Terminal"}),
    "cursor": frozenset({"Cursor"}),
}


@dataclass(frozen=True)
class RunningApp:
    """A running GUI application as observed by NSWorkspace."""

    bundle_id: str | None  # None for unusual processes without a bundle
    display_name: str
    is_foreground: bool = False


@dataclass(frozen=True)
class AppSelector:
    """A user-configured app target — either by bundle ID or display name."""

    kind: Literal["bundle_id", "display_name"]
    value: str


def is_valid_bundle_id(s: str) -> bool:
    """True if `s` is a safe bundle identifier (no injection characters)."""
    if not s:
        return False
    return bool(_BUNDLE_ID_RE.match(s))


def sort_apps_for_manifest(apps: list[RunningApp]) -> list[RunningApp]:
    """Stable case-insensitive sort by display name."""
    return sorted(apps, key=lambda a: (a.display_name.lower(), a.display_name))


def expand_aliases(names: list[str]) -> frozenset[str]:
    """Expand each name to itself plus any known casual aliases."""
    expanded: set[str] = set(names)
    for name in names:
        expanded |= _PROCESS_ALIASES.get(name.lower(), frozenset())
    return frozenset(expanded)


def name_in_list(name: str, names: list[str]) -> bool:
    """True if `name` matches `names` after alias expansion, case-insensitively."""
    expanded = expand_aliases(names)
    if name in expanded:
        return True
    return name.lower() in {candidate.lower() for candidate in expanded}


def app_matches_selector(app: RunningApp, selector: AppSelector) -> bool:
    """True if `app` is the target described by `selector`."""
    if selector.kind == "bundle_id":
        return app.bundle_id == selector.value
    # display_name: alias-aware case-insensitive match
    return name_in_list(app.display_name, [selector.value])
