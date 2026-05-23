"""Tests for domain.manifest — parse and format."""

from ctimeli.domain.manifest import format_manifest, parse_manifest


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
