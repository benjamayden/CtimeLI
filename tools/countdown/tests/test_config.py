"""Tests for domain.config — AppConfig parsing and merge."""

import pytest

from countdown.domain.apps import AppSelector
from countdown.domain.config import AppConfig


def _dn(value: str) -> AppSelector:
    return AppSelector(kind="display_name", value=value)


def _bid(value: str) -> AppSelector:
    return AppSelector(kind="bundle_id", value=value)


def test_defaults_when_mapping_empty():
    cfg, warnings = AppConfig.from_mapping({})
    assert cfg == AppConfig()
    assert warnings == []


def test_float_and_bool_parsing():
    cfg, _ = AppConfig.from_mapping({"STROKE_WIDTH": "10", "BLOCK_ON_END": "true"})
    assert cfg.stroke_width == 10.0
    assert cfg.block_on_end is True


@pytest.mark.parametrize("raw,expected", [("yes", True), ("1", True), ("on", True), ("no", False), ("", False)])
def test_bool_truthiness(raw, expected):
    cfg, _ = AppConfig.from_mapping({"BLOCK_ON_END": raw})
    assert cfg.block_on_end is expected


def test_csv_parsing_display_names():
    cfg, warnings = AppConfig.from_mapping({"BLOCK_END_MINIMIZE": "Chrome, Notes ,"})
    assert cfg.block_end_minimize == frozenset({_dn("Chrome"), _dn("Notes")})
    assert warnings == []


def test_csv_parsing_with_manifest_resolves_bundle_id():
    manifest = {1: "com.google.Chrome", 2: "com.apple.Notes"}
    cfg, warnings = AppConfig.from_mapping({"BLOCK_END_QUIT": "1,2"}, manifest=manifest)
    assert cfg.block_end_quit == frozenset({
        _bid("com.google.Chrome"),
        _bid("com.apple.Notes"),
    })
    assert warnings == []


def test_csv_parsing_stale_index_emits_warning():
    manifest = {1: "com.google.Chrome"}
    cfg, warnings = AppConfig.from_mapping({"BLOCK_END_QUIT": "99"}, manifest=manifest)
    assert cfg.block_end_quit == frozenset()
    assert any("99" in w for w in warnings)


def test_csv_parsing_mixed_numeric_and_display():
    manifest = {1: "com.google.Chrome"}
    cfg, warnings = AppConfig.from_mapping(
        {"BLOCK_END_HIDE": "1,safari"}, manifest=manifest
    )
    assert _bid("com.google.Chrome") in cfg.block_end_hide
    assert _dn("safari") in cfg.block_end_hide
    assert warnings == []


def test_csv_parsing_no_manifest_numeric_is_unresolved():
    cfg, warnings = AppConfig.from_mapping({"BLOCK_END_QUIT": "1"})
    assert cfg.block_end_quit == frozenset()
    assert any("1" in w for w in warnings)


def test_invalid_block_end_action_falls_back():
    cfg, _ = AppConfig.from_mapping({"BLOCK_END_DEFAULT": "banana"})
    assert cfg.block_end_default == "minimize"


def test_pulse_ramp_preset():
    cfg, _ = AppConfig.from_mapping({"PULSE_RAMP": "late"})
    assert cfg.pulse_ramp_power == 3.0
    cfg, _ = AppConfig.from_mapping({"PULSE_RAMP": "linear"})
    assert cfg.pulse_ramp_power == 1.0


def test_pulse_ramp_power_overrides_preset():
    cfg, _ = AppConfig.from_mapping({"PULSE_RAMP": "late", "PULSE_RAMP_POWER": "2"})
    assert cfg.pulse_ramp_power == 2.0


def test_merge_applies_non_none_overrides():
    merged = AppConfig().merge(stroke_width=20.0, red_zone_fraction=None)
    assert merged.stroke_width == 20.0
    assert merged.red_zone_fraction == AppConfig().red_zone_fraction


def test_merge_rejects_unknown_keys():
    with pytest.raises(ValueError, match="unknown AppConfig override"):
        AppConfig().merge(stoke_width=20.0)  # deliberate typo


def test_config_is_immutable():
    cfg = AppConfig()
    with pytest.raises(Exception):
        cfg.stroke_width = 99  # frozen dataclass
