"""Tests for ctimeli.cli — argument dispatch."""

from ctimeli import cli


def test_main_empty_argv_runs_watch(monkeypatch):
    seen: list[str] = []

    monkeypatch.delenv("CTIMELI_WATCH_FOREGROUND", raising=False)
    monkeypatch.delenv("CTIMELI_WATCH_CHILD", raising=False)
    monkeypatch.setattr(
        cli, "request_watch_launch_permissions", lambda _config: seen.append("perms")
    )
    monkeypatch.setattr(
        "ctimeli.adapters.system.detach.spawn_detached_watch",
        lambda _argv: seen.append("detach"),
    )

    assert cli.main([]) == 0
    assert seen == ["perms", "detach"]


def test_main_help_exits_zero(capsys):
    assert cli.main(["--help"]) == 0
    assert "ctimeli watch" in capsys.readouterr().out


def test_main_still_runs_countdown_with_time(monkeypatch):
    monkeypatch.setattr(
        cli,
        "run_one_shot",
        lambda _config, _target: 0,
    )
    assert cli.main(["15"]) == 0
