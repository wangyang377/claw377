from __future__ import annotations

from pathlib import Path

from claw377 import __version__
from claw377.app_paths import app_home, config_env_path
from claw377.loop import main


def test_version_flag(capsys) -> None:
    exit_code = main(["--version"])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.out.strip() == f"claw377 {__version__}"


def test_print_paths_uses_custom_home(monkeypatch, capsys, tmp_path: Path) -> None:
    monkeypatch.setenv("CLAW_HOME", str(tmp_path / "claw-home"))
    exit_code = main(["--print-paths"])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert f"app_home={app_home()}" in captured.out
    assert f"config={config_env_path()}" in captured.out
    assert (tmp_path / "claw-home" / "config.env").exists()
