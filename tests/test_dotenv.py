"""Tests for adapters.system.dotenv — .env file parsing."""

from pathlib import Path

from ctimeli.adapters.system.dotenv import DotEnvSource, _strip_inline_comment
from ctimeli.domain.config import AppConfig


def test_strip_inline_comment():
    assert _strip_inline_comment("true  # enable") == "true"
    assert _strip_inline_comment('6.0  # px') == "6.0"
    assert _strip_inline_comment('"hash#inside"') == '"hash#inside"'
    assert _strip_inline_comment("no-comment") == "no-comment"


def test_dotenv_strips_inline_comments(tmp_path: Path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "BLOCK_ON_END=true  # overlay at zero\n"
        "STROKE_WIDTH=6.0  # px\n",
        encoding="utf-8",
    )
    values = DotEnvSource(env_file).values()
    cfg, _ = AppConfig.from_mapping(values)
    assert cfg.block_on_end is True
    assert cfg.stroke_width == 6.0
