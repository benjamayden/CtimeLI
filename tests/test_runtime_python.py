"""Tests for stable venv python selection (macOS TCC identity)."""

from ctimeli.adapters.system.runtime import runtime_python


def test_runtime_python_prefers_venv_shim(tmp_path, monkeypatch):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    framework = tmp_path / "Frameworks" / "Python.framework" / "Versions" / "3.14" / "bin"
    framework.mkdir(parents=True)
    real = framework / "python3.14"
    real.write_text("")
    shim = bin_dir / "python3.14"
    shim.symlink_to(real)
    (bin_dir / "python").symlink_to("python3.14")

    monkeypatch.setattr("sys.executable", str(shim))
    assert runtime_python() == str(bin_dir / "python")


def test_runtime_python_keeps_non_venv_executable(monkeypatch):
    exe = "/usr/local/bin/python3.12"
    monkeypatch.setattr("sys.executable", exe)
    assert runtime_python() == exe
