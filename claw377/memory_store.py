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
