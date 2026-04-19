from __future__ import annotations

import json
from pathlib import Path

from .app_paths import current_workspace, memory_dir, memory_file


class MemoryStore:
    def __init__(self, workspace: Path | None = None):
        self.workspace = workspace or current_workspace()
        self.dir = memory_dir(self.workspace)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.memory_file = memory_file(self.workspace)
        self.history_file = self.dir / "history.jsonl"
        self.memory_cursor_file = self.dir / ".memory_cursor"

    def ensure_memory_file(self, default_content: str) -> None:
        if not self.memory_file.exists():
            self.memory_file.write_text(default_content, encoding="utf-8")

    def read_memory(self) -> str:
        if not self.memory_file.exists():
            return ""
        return self.memory_file.read_text(encoding="utf-8").strip()

    def write_memory(self, content: str) -> None:
        self.memory_file.write_text(content, encoding="utf-8")

    def append_history(self, summary: str, *, message_count: int) -> None:
        record = {
            "summary": summary,
            "message_count": message_count,
        }
        with self.history_file.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    def read_history(self) -> list[dict]:
        if not self.history_file.exists():
            return []
        records: list[dict] = []
        for line in self.history_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            records.append(json.loads(line))
        return records

    def read_memory_cursor(self) -> int:
        if not self.memory_cursor_file.exists():
            return 0
        text = self.memory_cursor_file.read_text(encoding="utf-8").strip()
        return int(text) if text else 0

    def write_memory_cursor(self, value: int) -> None:
        self.memory_cursor_file.write_text(str(value), encoding="utf-8")

    def pending_history(self) -> list[dict]:
        history = self.read_history()
        return history[self.read_memory_cursor() :]
