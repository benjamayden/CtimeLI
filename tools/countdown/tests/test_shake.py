"""Tests for domain.shake — the pure wiggle-offset generator."""

from countdown.domain.config import AppConfig
from countdown.domain.shake import ShakeMotion

CFG = AppConfig()
FRAME = 1.0 / 60.0


def test_zero_intensity_is_no_offset():
    motion = ShakeMotion(CFG)
    assert motion.offset(0.0, FRAME) == (0.0, 0.0)


def test_offset_stays_within_amplitude():
    motion = ShakeMotion(CFG)
    for _ in range(600):
        dx, dy = motion.offset(1.0, FRAME)
        assert abs(dx) <= CFG.shake_max_x + 1e-9
        assert abs(dy) <= CFG.shake_max_y + 1e-9


def test_offset_actually_moves():
    motion = ShakeMotion(CFG)
    first = motion.offset(1.0, FRAME)
    later = [motion.offset(1.0, FRAME) for _ in range(60)]
    assert any(sample != first for sample in later)


def test_reset_returns_to_rest():
    motion = ShakeMotion(CFG)
    for _ in range(60):
        motion.offset(1.0, FRAME)
    motion.reset()
    assert motion.offset(0.0, FRAME) == (0.0, 0.0)
