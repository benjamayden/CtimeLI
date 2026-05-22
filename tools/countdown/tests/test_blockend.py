"""Tests for domain.blockend — see docs/domain.md section 6."""

from countdown.domain.apps import AppSelector, RunningApp, expand_aliases, name_in_list
from countdown.domain.blockend import (
    BlockAction,
    block_end_summary,
    plan_block_end,
)
from countdown.domain.config import AppConfig

# Helpers — construct AppSelectors with less verbosity in test bodies.
def _dn(value: str) -> AppSelector:
    return AppSelector(kind="display_name", value=value)


def _bid(value: str) -> AppSelector:
    return AppSelector(kind="bundle_id", value=value)


# Helpers — build RunningApp fixtures.
def _app(display_name: str, bundle_id: str | None = None, is_foreground: bool = False) -> RunningApp:
    return RunningApp(bundle_id=bundle_id, display_name=display_name, is_foreground=is_foreground)


def test_expand_aliases():
    expanded = expand_aliases(["chrome"])
    assert "Google Chrome" in expanded
    assert "Chrome" in expanded


def test_name_in_list_is_alias_and_case_aware():
    assert name_in_list("Google Chrome", ["chrome"]) is True
    assert name_in_list("google chrome", ["Chrome"]) is True
    assert name_in_list("Safari", ["chrome"]) is False


def test_plan_precedence_quit_beats_default():
    cfg = AppConfig(
        block_end_quit=frozenset({_dn("chrome")}),
        block_end_default="minimize",
    )
    plan = plan_block_end(
        running_apps=[
            _app("Google Chrome", "com.google.Chrome"),
            _app("Notes", "com.apple.Notes"),
        ],
        foreground_apps=[
            _app("Notes", "com.apple.Notes", is_foreground=True),
            _app("Finder", "com.apple.finder", is_foreground=True),
        ],
        cfg=cfg,
    )
    bundle_ids = {bid for bid, _ in plan}
    assert ("com.google.Chrome", BlockAction.QUIT) in plan
    assert ("com.apple.Notes", BlockAction.MINIMIZE) in plan
    assert ("com.apple.finder", BlockAction.MINIMIZE) in plan


def test_plan_skips_system_apps():
    cfg = AppConfig(block_end_default="minimize")
    plan = plan_block_end(
        running_apps=[
            _app("Dock", "com.apple.dock"),
            _app("WindowManager", "com.apple.windowmanager"),
        ],
        foreground_apps=[
            _app("Dock", "com.apple.dock", is_foreground=True),
            _app("Finder", "com.apple.finder", is_foreground=True),
        ],
        cfg=cfg,
    )
    acted = {bid for bid, _ in plan}
    assert "com.apple.dock" not in acted
    assert "com.apple.windowmanager" not in acted
    assert "com.apple.finder" in acted


def test_plan_honours_extra_skip():
    cfg = AppConfig(block_end_default="minimize")
    plan = plan_block_end(
        running_apps=[
            _app("Terminal", "com.apple.Terminal"),
            _app("Notes", "com.apple.Notes"),
        ],
        foreground_apps=[
            _app("Terminal", "com.apple.Terminal", is_foreground=True),
            _app("Notes", "com.apple.Notes", is_foreground=True),
        ],
        cfg=cfg,
        extra_skip=frozenset({_dn("Terminal")}),
    )
    acted = {bid for bid, _ in plan}
    assert acted == {"com.apple.Notes"}


def test_plan_default_skip_yields_empty_plan():
    cfg = AppConfig(block_end_default="skip")
    plan = plan_block_end(
        running_apps=[_app("Notes", "com.apple.Notes")],
        foreground_apps=[_app("Notes", "com.apple.Notes", is_foreground=True)],
        cfg=cfg,
    )
    assert plan == []


def test_plan_does_not_assign_an_app_twice():
    cfg = AppConfig(block_end_default="minimize")
    plan = plan_block_end(
        running_apps=[_app("Notes", "com.apple.Notes")],
        foreground_apps=[
            _app("Notes", "com.apple.Notes", is_foreground=True),
            _app("Notes", "com.apple.Notes", is_foreground=True),
        ],
        cfg=cfg,
    )
    assert plan.count(("com.apple.Notes", BlockAction.MINIMIZE)) == 1


def test_plan_background_app_not_in_explicit_list_gets_no_action():
    # Pass 2 (default) only sweeps foreground apps — a background app not in any
    # explicit list must not be touched (the two-pass distinction from docs/domain.md §6).
    cfg = AppConfig(block_end_default="minimize")
    plan = plan_block_end(
        running_apps=[
            _app("Notes", "com.apple.Notes"),
            _app("Spotify", "com.spotify.client"),
        ],
        foreground_apps=[_app("Notes", "com.apple.Notes", is_foreground=True)],
        cfg=cfg,
    )
    acted = {bid for bid, _ in plan}
    assert "com.spotify.client" not in acted
    assert "com.apple.Notes" in acted


def test_plan_explicit_list_acts_on_background_app():
    # Pass 1 fires on every running app — an explicit quit/hide/minimize config
    # applies even if the app is not in the foreground.
    cfg = AppConfig(block_end_quit=frozenset({_dn("spotify")}))
    plan = plan_block_end(
        running_apps=[_app("Spotify", "com.spotify.client")],
        foreground_apps=[],
        cfg=cfg,
    )
    assert ("com.spotify.client", BlockAction.QUIT) in plan


def test_plan_emits_bundle_id_not_display_name():
    # The plan tuples must carry bundle IDs, never localised display names.
    cfg = AppConfig(block_end_quit=frozenset({_dn("chrome")}))
    plan = plan_block_end(
        running_apps=[_app("Google Chrome", "com.google.Chrome")],
        foreground_apps=[],
        cfg=cfg,
    )
    assert len(plan) == 1
    bundle_id, action = plan[0]
    assert bundle_id == "com.google.Chrome"
    assert "Google Chrome" not in bundle_id


def test_plan_skips_app_without_bundle_id():
    # RunningApps without a bundle_id cannot be targeted and must be excluded.
    cfg = AppConfig(block_end_default="minimize")
    plan = plan_block_end(
        running_apps=[_app("WeirdApp", bundle_id=None)],
        foreground_apps=[_app("WeirdApp", bundle_id=None, is_foreground=True)],
        cfg=cfg,
    )
    assert plan == []


def test_plan_bundle_id_selector_beats_default():
    # Explicit bundle_id selector in config matches correctly.
    cfg = AppConfig(
        block_end_quit=frozenset({_bid("com.google.Chrome")}),
        block_end_default="minimize",
    )
    plan = plan_block_end(
        running_apps=[_app("Google Chrome", "com.google.Chrome")],
        foreground_apps=[],
        cfg=cfg,
    )
    assert ("com.google.Chrome", BlockAction.QUIT) in plan


def test_plan_legacy_display_name_still_works():
    # AppSelector(display_name="chrome") matches Google Chrome via alias table.
    cfg = AppConfig(block_end_hide=frozenset({_dn("chrome")}))
    plan = plan_block_end(
        running_apps=[_app("Google Chrome", "com.google.Chrome")],
        foreground_apps=[],
        cfg=cfg,
    )
    assert ("com.google.Chrome", BlockAction.HIDE) in plan


def test_summary_phrasing():
    assert block_end_summary({"minimize": 3, "hide": 0, "quit": 1}) == (
        "Block end: minimized 3 windows, quit 1 app."
    )
    assert block_end_summary({"minimize": 1, "hide": 0, "quit": 0}) == (
        "Block end: minimized 1 window."
    )
    assert block_end_summary({"minimize": 0, "hide": 0, "quit": 0}) is None
