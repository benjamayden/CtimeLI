"""Tests for domain.config — AppConfig parsing and merge."""

import pytest

from countdown.domain.config import AppConfig


def test_defaults_when_mapping_empty():
    cfg = AppConfig.from_mapping({})
    assert cfg == AppConfig()


def test_float_and_bool_parsing():
    cfg = AppConfig.from_mapping({"STROKE_WIDTH": "10", "BLOCK_ON_END": "true"})
    assert cfg.stroke_width == 10.0
    assert cfg.block_on_end is True


@pytest.mark.parametrize("raw,expected", [("yes", True), ("1", True), ("on", True), ("no", False), ("", False)])
def test_bool_truthiness(raw, expected):
    assert AppConfig.from_mapping({"BLOCK_ON_END": raw}).block_on_end is expected


def test_csv_parsing():
    cfg = AppConfig.from_mapping({"BLOCK_END_MINIMIZE": "Chrome, Notes ,"})
    assert cfg.block_end_minimize == frozenset({"Chrome", "Notes"})


def test_invalid_block_end_action_falls_back():
    cfg = AppConfig.from_mapping({"BLOCK_END_DEFAULT": "banana"})
    assert cfg.block_end_default == "minimize"


def test_pulse_ramp_preset():
    assert AppConfig.from_mapping({"PULSE_RAMP": "late"}).pulse_ramp_power == 3.0
    assert AppConfig.from_mapping({"PULSE_RAMP": "linear"}).pulse_ramp_power == 1.0


def test_pulse_ramp_power_overrides_preset():
    cfg = AppConfig.from_mapping({"PULSE_RAMP": "late", "PULSE_RAMP_POWER": "2"})
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
