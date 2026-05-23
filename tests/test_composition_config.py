"""Tests for composition root config path resolution."""

from ctimeli.composition import _ENV_PATH, build_config


def test_env_path_is_repo_root():
    assert _ENV_PATH.name == ".env"
    assert _ENV_PATH.parent.name != "src"


def test_build_config_reads_repo_env():
    if not _ENV_PATH.is_file():
        return
    cfg, _ = build_config()
    assert cfg.block_on_end is True
