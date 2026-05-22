"""Block-end planning — pure. See docs/domain.md section 6.

This decides *which app gets which action*. Executing the plan (AppleScript,
terminate calls) is the BlockEndExecutor adapter, not this module.
"""

from __future__ import annotations

from collections.abc import Iterable
from enum import Enum

from .apps import AppSelector, RunningApp, app_matches_selector, expand_aliases, name_in_list
from .config import AppConfig


class BlockAction(Enum):
    """What block-end does to an app. SKIP entries never reach a plan."""

    SKIP = "skip"
    QUIT = "quit"
    HIDE = "hide"
    MINIMIZE = "minimize"


# Never touched, regardless of config — checked against display_name.
SYSTEM_SKIP: frozenset[str] = frozenset(
    {"SystemUIServer", "WindowManager", "Dock", "loginwindow", "Python", "python"}
)


def plan_block_end(
    running_apps: Iterable[RunningApp],
    foreground_apps: Iterable[RunningApp],
    cfg: AppConfig,
    extra_skip: Iterable[AppSelector] = (),
) -> list[tuple[str, BlockAction]]:
    """Decide the ordered (bundle_id, action) plan for a block-end tidy.

    Pass 1: explicit .env selectors, over every running app (incl. windowless).
    Pass 2: the default action, over foreground apps only.
    SKIP-ed apps and SKIP actions never appear in the returned plan.
    Apps without a bundle_id that match a selector are silently excluded
    (no safe AppleScript target).
    """
    all_skip: frozenset[AppSelector] = cfg.block_end_skip | frozenset(extra_skip)
    default = BlockAction(cfg.block_end_default)

    plan: list[tuple[str, BlockAction]] = []
    assigned: set[str] = set()  # tracks assigned bundle_ids

    def _is_skipped(app: RunningApp) -> bool:
        if app.display_name in SYSTEM_SKIP:
            return True
        return any(app_matches_selector(app, sel) for sel in all_skip)

    def assign(app: RunningApp, action: BlockAction) -> None:
        bundle_id = app.bundle_id
        if bundle_id is None:
            return  # can't target without a bundle ID
        if bundle_id in assigned or _is_skipped(app):
            return
        assigned.add(bundle_id)
        if action is not BlockAction.SKIP:
            plan.append((bundle_id, action))

    for app in running_apps:
        if any(app_matches_selector(app, sel) for sel in cfg.block_end_quit):
            assign(app, BlockAction.QUIT)
        elif any(app_matches_selector(app, sel) for sel in cfg.block_end_hide):
            assign(app, BlockAction.HIDE)
        elif any(app_matches_selector(app, sel) for sel in cfg.block_end_minimize):
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
