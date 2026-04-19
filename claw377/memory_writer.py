from __future__ import annotations

import os

from litellm import completion

from .memory_store import MemoryStore

MEMORY_UPDATE_BATCH_SIZE = 3


class LongTermMemoryWriter:
    def __init__(self, store: MemoryStore, batch_size: int = MEMORY_UPDATE_BATCH_SIZE):
        self.store = store
        self.batch_size = batch_size

    def maybe_update(self) -> bool:
        pending = self.store.pending_history()
        if len(pending) < self.batch_size:
            return False

        batch = pending[: self.batch_size]
        updated_memory = self._rewrite_memory(
            current_memory=self.store.read_memory(),
            summaries=[item.get("summary", "") for item in batch],
        )
        self.store.write_memory(updated_memory)
        self.store.write_memory_cursor(self.store.read_memory_cursor() + len(batch))
        return True

    def _rewrite_memory(self, *, current_memory: str, summaries: list[str]) -> str:
        summary_block = "\n\n".join(
            f"{idx}. {summary}" for idx, summary in enumerate(summaries, start=1)
        )
        response = completion(
            model=os.getenv("MODEL_NAME") or os.getenv("LITELLM_MODEL"),
            messages=[
                {
                    "role": "user",
                    "content": (
                        "Update the long-term MEMORY.md using the archived conversation summaries below. "
                        "Keep only durable preferences, stable project facts, important constraints, and "
                        "confirmed decisions. Do not keep transient chat, temporary tool output, or one-off details. "
                        "Return the full updated MEMORY.md content only.\n\n"
                        f"Current MEMORY.md:\n{current_memory}\n\n"
                        f"New archived summaries:\n{summary_block}"
                    ),
                }
            ],
        )
        return response.choices[0].message.content or current_memory
