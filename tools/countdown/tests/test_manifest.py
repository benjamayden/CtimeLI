"""Tests for domain.manifest — parse, format, resolve."""

import pytest

from countdown.domain.apps import AppSelector
from countdown.domain.manifest import format_manifest, parse_manifest, resolve_block_end_csv


def _dn(v: str) -> AppSelector:
    return AppSelector(kind="display_name", value=v)


def _bid(v: str) -> AppSelector:
    return AppSelector(kind="bundle_id", value=v)


# -- parse_manifest -----------------------------------------------------------

def test_parse_happy_path():
    text = "1=com.google.Chrome\n2=com.apple.Notes\n"
    assert parse_manifest(text) == {1: "com.google.Chrome", 2: "com.apple.Notes"}


def test_parse_ignores_comments():
    text = "# this is a comment\n1=com.foo\n"
    assert parse_manifest(text) == {1: "com.foo"}


def test_parse_ignores_blank_lines():
    text = "\n1=com.foo\n\n2=com.bar\n"
    assert parse_manifest(text) == {1: "com.foo", 2: "com.bar"}


def test_parse_ignores_line_without_equals():
    text = "1=com.foo\njust text here\n2=com.bar\n"
    assert parse_manifest(text) == {1: "com.foo", 2: "com.bar"}


def test_parse_ignores_non_integer_index():
    text = "abc=com.foo\n1=com.bar\n"
    assert parse_manifest(text) == {1: "com.bar"}


def test_parse_ignores_invalid_bundle_id():
    text = '1=com.evil" & do shell\n2=com.good\n'
    assert parse_manifest(text) == {2: "com.good"}


def test_parse_duplicate_index_last_wins():
    text = "1=com.first\n1=com.second\n"
    assert parse_manifest(text) == {1: "com.second"}


def test_parse_empty_text():
    assert parse_manifest("") == {}


# -- format_manifest ----------------------------------------------------------

def test_format_round_trip():
    original = {1: "com.google.Chrome", 3: "com.apple.finder"}
    text = format_manifest(original)
    parsed = parse_manifest(text)
    assert parsed == original


def test_format_indices_sorted():
    text = format_manifest({3: "com.c", 1: "com.a", 2: "com.b"})
    lines = [l for l in text.splitlines() if not l.startswith("#") and l.strip()]
    assert lines == ["1=com.a", "2=com.b", "3=com.c"]


def test_format_includes_comment_header():
    text = format_manifest({1: "com.foo"})
    assert text.splitlines()[0].startswith("#")


# -- resolve_block_end_csv ----------------------------------------------------

def test_resolve_numeric_tokens_via_manifest():
    manifest = {1: "com.google.Chrome", 3: "com.apple.Notes"}
    selectors, unresolved = resolve_block_end_csv("1,3", manifest)
    assert selectors == frozenset({_bid("com.google.Chrome"), _bid("com.apple.Notes")})
    assert unresolved == []


def test_resolve_display_name_tokens_no_manifest():
    selectors, unresolved = resolve_block_end_csv("Chrome, Notes", {})
    assert selectors == frozenset({_dn("Chrome"), _dn("Notes")})
    assert unresolved == []


def test_resolve_mixed_numeric_and_display():
    manifest = {1: "com.google.Chrome"}
    selectors, unresolved = resolve_block_end_csv("1,safari", manifest)
    assert _bid("com.google.Chrome") in selectors
    assert _dn("safari") in selectors
    assert unresolved == []


def test_resolve_stale_index_returns_unresolved():
    selectors, unresolved = resolve_block_end_csv("99", {})
    assert selectors == frozenset()
    assert unresolved == ["99"]


def test_resolve_empty_csv():
    selectors, unresolved = resolve_block_end_csv("", {})
    assert selectors == frozenset()
    assert unresolved == []


def test_resolve_whitespace_only():
    selectors, unresolved = resolve_block_end_csv("   ", {})
    assert selectors == frozenset()
    assert unresolved == []


def test_resolve_trailing_comma_ignored():
    selectors, _ = resolve_block_end_csv("chrome,", {})
    assert selectors == frozenset({_dn("chrome")})
