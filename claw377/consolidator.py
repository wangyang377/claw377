from __future__ import annotations

import json
import os

from litellm import completion

from .memory_store import MemoryStore
from .session import Session
from .tools.compact import estimate_tokens


class Consolidator:
    def __init__(self, store: MemoryStore, threshold: int):
        self.store = store
        self.threshold = threshold

    def maybe_consolidate(
        self,
        session: Session,
        *,
        build_prompt_messages,
        current_message: str | None = None,
    ) -> bool:
        changed = False
        while True:
            prompt_messages = build_prompt_messages(
                session.active_messages(),
                recent_archive_summary=session.recent_archive_summary,
                current_message=current_message,
            )
            if estimate_tokens(prompt_messages) <= self.threshold:
                return changed

            boundary = self._pick_boundary(session)
            if boundary is None:
                return changed

            chunk = session.messages[session.last_consolidated : boundary]
            summary = self._summarize_chunk(chunk)
            self.store.append_history(summary, message_count=len(chunk))
            session.recent_archive_summary = summary
            session.last_consolidated = boundary
            changed = True

    @staticmethod
    def _pick_boundary(session: Session) -> int | None:
        start = session.last_consolidated
        if start >= len(session.messages):
            return None

        for idx in range(start + 1, len(session.messages)):
            if session.messages[idx].get("role") == "user":
                return idx
        return None

    @staticmethod
    def _format_messages(messages: list[dict]) -> str:
        lines: list[str] = []
        for message in messages:
            content = message.get("content", "")
            if not content:
                continue
            lines.append(f"{message.get('role', 'unknown').upper()}: {content}")
        return "\n\n".join(lines)

    def _summarize_chunk(self, messages: list[dict]) -> str:
        response = completion(
            model=os.getenv("MODEL_NAME") or os.getenv("LITELLM_MODEL"),
            messages=[
                {
                    "role": "user",
                    "content": (
                        "Summarize this archived conversation chunk for near-term continuity. "
                        "Preserve: current task, key decisions, unfinished work, and important facts. "
                        "Be concise.\n\n"
                        f"{self._format_messages(messages)}"
                    ),
                }
            ],
        )
        return response.choices[0].message.content or "(no summary)"
