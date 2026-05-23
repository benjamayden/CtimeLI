"""Tests for domain.config — AppConfig parsing and merge."""

import pytest

from ctimeli.domain.config import AppConfig


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


def test_work_wifi_and_hard_stop_config_parsing():
    cfg, _ = AppConfig.from_mapping({
        "WORK_WIFI_SSIDS": "Office-Guest, CorpWiFi",
        "HARD_STOP_ENABLED": "true",
        "HARD_STOP_TIME": "22:00",
        "HARD_STOP_WARNING_MINS": "45",
        "HARD_STOP_STROKE_R": "0.9",
    })
    assert cfg.work_wifi_ssids == frozenset({"Office-Guest", "CorpWiFi"})
    assert cfg.hard_stop_enabled is True
    assert cfg.hard_stop_time.hour == 22
    assert cfg.hard_stop_warning_mins == 45.0
    assert cfg.hard_stop_stroke_r == 0.9


def test_config_is_immutable():
    cfg = AppConfig()
    with pytest.raises(Exception):
        cfg.stroke_width = 99  # frozen dataclass
