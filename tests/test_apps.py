"""Tests for domain.apps — RunningApp, AppSelector, bundle-ID validation."""

import pytest

from ctimeli.domain.apps import (
    AppSelector,
    RunningApp,
    app_matches_selector,
    is_valid_bundle_id,
    sort_apps_for_manifest,
)


# -- is_valid_bundle_id -------------------------------------------------------

@pytest.mark.parametrize("bundle_id", [
    "com.google.Chrome",
    "com.apple.finder",
    "net.kovidgoyal.kitty",
    "com.todesktop.213803m5fafj212j0w1p2j7q8",
    "a",
    "A.B.C",
    "com.foo-bar",
])
def test_valid_bundle_ids(bundle_id: str):
    assert is_valid_bundle_id(bundle_id) is True


@pytest.mark.parametrize("bundle_id", [
    "",
    "com.evil\" & do shell script \"rm -rf ~",
    "foo bar",
    "com.foo&bar",
    "com.foo;bar",
    "com.foo/bar",
    'com.foo"bar',
    "com.foo\nbar",
    "com.foo|bar",
])
def test_invalid_bundle_ids(bundle_id: str):
    assert is_valid_bundle_id(bundle_id) is False


# -- sort_apps_for_manifest ---------------------------------------------------

def test_sort_apps_case_insensitive():
    apps = [
        RunningApp("com.b", "Zoom"),
        RunningApp("com.a", "apps"),
        RunningApp("com.c", "Finder"),
    ]
    sorted_apps = sort_apps_for_manifest(apps)
    names = [a.display_name for a in sorted_apps]
    assert names == ["apps", "Finder", "Zoom"]


def test_sort_apps_stable_on_ties():
    # Two apps with the same lower-case name but different casing are both included.
    apps = [
        RunningApp("com.a", "Notes"),
        RunningApp("com.b", "notes"),
    ]
    sorted_apps = sort_apps_for_manifest(apps)
    assert len(sorted_apps) == 2
    assert sorted_apps[0].display_name == "Notes"
    assert sorted_apps[1].display_name == "notes"


# -- app_matches_selector -----------------------------------------------------

def test_matches_by_bundle_id():
    app = RunningApp("com.google.Chrome", "Google Chrome")
    sel = AppSelector(kind="bundle_id", value="com.google.Chrome")
    assert app_matches_selector(app, sel) is True


def test_no_match_wrong_bundle_id():
    app = RunningApp("com.google.Chrome", "Google Chrome")
    sel = AppSelector(kind="bundle_id", value="com.mozilla.Firefox")
    assert app_matches_selector(app, sel) is False


def test_bundle_id_selector_no_match_when_app_has_no_bundle():
    app = RunningApp(None, "SomeApp")
    sel = AppSelector(kind="bundle_id", value="com.some.app")
    assert app_matches_selector(app, sel) is False


def test_matches_by_display_name_exact():
    app = RunningApp("com.apple.Notes", "Notes")
    sel = AppSelector(kind="display_name", value="Notes")
    assert app_matches_selector(app, sel) is True


def test_matches_by_display_name_case_insensitive():
    app = RunningApp("com.apple.Notes", "Notes")
    sel = AppSelector(kind="display_name", value="notes")
    assert app_matches_selector(app, sel) is True


def test_matches_by_display_name_via_alias():
    app = RunningApp("com.google.Chrome", "Google Chrome")
    sel = AppSelector(kind="display_name", value="chrome")
    assert app_matches_selector(app, sel) is True


def test_display_name_selector_still_matches_app_without_bundle():
    app = RunningApp(None, "SomeApp")
    sel = AppSelector(kind="display_name", value="SomeApp")
    assert app_matches_selector(app, sel) is True
