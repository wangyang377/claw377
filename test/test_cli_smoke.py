from __future__ import annotations

from types import SimpleNamespace
from pathlib import Path

from claw377 import __version__
from claw377.app_paths import app_home, config_env_path
from claw377.context import default_memory_text
from claw377 import loop as loop_module
from claw377.loop import _handle_frontend_command, load_session, main, save_session
from claw377.memory_store import MemoryStore
from claw377.memory_writer import LongTermMemoryWriter
from claw377.session import Session


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


def test_load_session_restores_session_state(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("CLAW_HOME", str(tmp_path / "claw-home"))
    loop_module.memory_store = MemoryStore(tmp_path)
    loop_module.memory_store.ensure_memory_file(default_memory_text())
    session_meta = {
        "session_id": "test-session",
        "created_at": "2026-04-19T00:00:00+08:00",
        "updated_at": "2026-04-19T00:00:00+08:00",
        "model": "test-model",
        "workspace": str(tmp_path),
    }
    runtime_session = Session(
        messages=[{"role": "user", "content": "hello"}],
        last_consolidated=1,
        recent_archive_summary="summary",
    )
    path = app_home() / "sessions" / "test-session.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    save_session(session_meta, runtime_session, path)

    loaded_meta, loaded_session, loaded_path = load_session("test-session")

    assert loaded_meta["session_id"] == "test-session"
    assert loaded_session.messages == runtime_session.messages
    assert loaded_session.last_consolidated == 1
    assert loaded_session.recent_archive_summary == "summary"
    assert loaded_path == path


def test_resume_command_requires_session_id(capsys) -> None:
    action, payload = _handle_frontend_command("/resume")
    captured = capsys.readouterr()

    assert action == "handled"
    assert payload is None
    assert "Usage: /resume <session_id>" in captured.out


def test_memory_store_pending_history(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path)
    store.append_history("one", message_count=1)
    store.append_history("two", message_count=1)
    store.append_history("three", message_count=1)

    assert [item["summary"] for item in store.pending_history()] == ["one", "two", "three"]

    store.write_memory_cursor(2)
    assert [item["summary"] for item in store.pending_history()] == ["three"]


def test_long_term_memory_updates_after_three_archives(tmp_path: Path, monkeypatch) -> None:
    store = MemoryStore(tmp_path)
    store.write_memory("base memory")
    store.append_history("one", message_count=1)
    store.append_history("two", message_count=1)
    store.append_history("three", message_count=1)

    response = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="updated memory"))]
    )
    monkeypatch.setattr("claw377.memory_writer.completion", lambda **_: response)

    writer = LongTermMemoryWriter(store)
    assert writer.maybe_update() is True
    assert store.read_memory() == "updated memory"
    assert store.read_memory_cursor() == 3
