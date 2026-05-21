"""Tests for domain.blockend — see docs/domain.md section 6."""

from countdown.domain.blockend import (
    BlockAction,
    block_end_summary,
    expand_aliases,
    name_in_list,
    plan_block_end,
)
from countdown.domain.config import AppConfig


def test_expand_aliases():
    expanded = expand_aliases(["chrome"])
    assert "Google Chrome" in expanded
    assert "Chrome" in expanded


def test_name_in_list_is_alias_and_case_aware():
    assert name_in_list("Google Chrome", ["chrome"]) is True
    assert name_in_list("google chrome", ["Chrome"]) is True
    assert name_in_list("Safari", ["chrome"]) is False


def test_plan_precedence_quit_beats_default():
    cfg = AppConfig(block_end_quit=frozenset({"chrome"}), block_end_default="minimize")
    plan = plan_block_end(
        running_apps=["Google Chrome", "Notes"],
        foreground_apps=["Notes", "Finder"],
        cfg=cfg,
    )
    assert ("Google Chrome", BlockAction.QUIT) in plan
    assert ("Notes", BlockAction.MINIMIZE) in plan
    assert ("Finder", BlockAction.MINIMIZE) in plan


def test_plan_skips_system_apps():
    cfg = AppConfig(block_end_default="minimize")
    plan = plan_block_end(
        running_apps=["Dock", "WindowManager"],
        foreground_apps=["Dock", "Finder"],
        cfg=cfg,
    )
    acted = {name for name, _ in plan}
    assert "Dock" not in acted and "WindowManager" not in acted
    assert "Finder" in acted


def test_plan_honours_extra_skip():
    cfg = AppConfig(block_end_default="minimize")
    plan = plan_block_end(
        running_apps=["Terminal", "Notes"],
        foreground_apps=["Terminal", "Notes"],
        cfg=cfg,
        extra_skip=frozenset({"Terminal"}),
    )
    acted = {name for name, _ in plan}
    assert acted == {"Notes"}


def test_plan_default_skip_yields_empty_plan():
    cfg = AppConfig(block_end_default="skip")
    plan = plan_block_end(["Notes"], ["Notes", "Finder"], cfg)
    assert plan == []


def test_plan_does_not_assign_an_app_twice():
    cfg = AppConfig(block_end_default="minimize")
    plan = plan_block_end(["Notes"], ["Notes", "Notes"], cfg)
    assert plan.count(("Notes", BlockAction.MINIMIZE)) == 1


def test_summary_phrasing():
    assert block_end_summary({"minimize": 3, "hide": 0, "quit": 1}) == (
        "Block end: minimized 3 windows, quit 1 app."
    )
    assert block_end_summary({"minimize": 1, "hide": 0, "quit": 0}) == (
        "Block end: minimized 1 window."
    )
    assert block_end_summary({"minimize": 0, "hide": 0, "quit": 0}) is None
