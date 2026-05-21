"""Block-end planning — pure. See docs/domain.md section 6.

This decides *which app gets which action*. Executing the plan (AppleScript,
terminate calls) is the BlockEndExecutor adapter, not this module.
"""

from __future__ import annotations

from collections.abc import Iterable
from enum import Enum

from .config import AppConfig


class BlockAction(Enum):
    """What block-end does to an app. SKIP entries never reach a plan."""

    SKIP = "skip"
    QUIT = "quit"
    HIDE = "hide"
    MINIMIZE = "minimize"


# Never touched, regardless of config.
SYSTEM_SKIP: frozenset[str] = frozenset(
    {"SystemUIServer", "WindowManager", "Dock", "loginwindow", "Python", "python"}
)

# Casual .env names -> the System Events / NSWorkspace process names.
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


def expand_aliases(names: Iterable[str]) -> frozenset[str]:
    """Expand each name to itself plus any known aliases."""
    expanded: set[str] = set(names)
    for name in names:
        expanded |= _PROCESS_ALIASES.get(name.lower(), frozenset())
    return frozenset(expanded)


def name_in_list(name: str, names: Iterable[str]) -> bool:
    """True if `name` matches `names` after alias expansion, case-insensitively."""
    expanded = expand_aliases(names)
    if name in expanded:
        return True
    return name.lower() in {candidate.lower() for candidate in expanded}


def plan_block_end(
    running_apps: Iterable[str],
    foreground_apps: Iterable[str],
    cfg: AppConfig,
    extra_skip: Iterable[str] = (),
) -> list[tuple[str, BlockAction]]:
    """Decide the ordered (app, action) plan for a block-end tidy.

    Pass 1: explicit .env lists, over every running app (incl. windowless).
    Pass 2: the default action, over foreground apps only.
    SKIP-ed apps and SKIP actions never appear in the returned plan.
    """
    skip = frozenset(SYSTEM_SKIP | cfg.block_end_skip | frozenset(extra_skip))
    default = BlockAction(cfg.block_end_default)

    plan: list[tuple[str, BlockAction]] = []
    assigned: set[str] = set()

    def assign(app: str, action: BlockAction) -> None:
        if app in assigned or name_in_list(app, skip):
            return
        assigned.add(app)
        if action is not BlockAction.SKIP:
            plan.append((app, action))

    for app in running_apps:
        if name_in_list(app, cfg.block_end_quit):
            assign(app, BlockAction.QUIT)
        elif name_in_list(app, cfg.block_end_hide):
            assign(app, BlockAction.HIDE)
        elif name_in_list(app, cfg.block_end_minimize):
            assign(app, BlockAction.MINIMIZE)

    for app in foreground_apps:
        assign(app, default)

    return plan


def block_end_summary(counts: dict[str, int]) -> str | None:
    """One-line human summary of executed counts, or None if nothing happened."""
    parts: list[str] = []
    if counts.get("minimize"):
        n = counts["minimize"]
        parts.append(f"minimized {n} window{'s' if n != 1 else ''}")
    if counts.get("hide"):
        n = counts["hide"]
        parts.append(f"hid {n} app{'s' if n != 1 else ''}")
    if counts.get("quit"):
        n = counts["quit"]
        parts.append(f"quit {n} app{'s' if n != 1 else ''}")
    if not parts:
        return None
    return "Block end: " + ", ".join(parts) + "."
