from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Session:
    messages: list[dict[str, Any]] = field(default_factory=list)
    last_consolidated: int = 0
    recent_archive_summary: str = ""

    def add(self, message: dict[str, Any]) -> None:
        self.messages.append(message)

    def active_messages(self) -> list[dict[str, Any]]:
        return self.messages[self.last_consolidated :]
