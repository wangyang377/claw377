"""Compact tool — lets the model trigger conversation compression."""

import json
import os
import time
from pathlib import Path

from litellm import completion

from ..app_paths import transcripts_dir

TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "compact",
        "description": (
            "Compress conversation history into a concise summary to free up context window. "
            "Use when the conversation is getting long or before starting a new major task."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "focus": {
                    "type": "string",
                    "description": "What to especially preserve in the summary",
                },
            },
        },
    },
}


def estimate_tokens(messages: list[dict]) -> int:
    return len(json.dumps(messages, ensure_ascii=False, default=str)) // 4


def _save_transcript(messages: list[dict]) -> Path:
    transcript_dir = transcripts_dir()
    transcript_dir.mkdir(parents=True, exist_ok=True)
    path = transcript_dir / f"transcript_{int(time.time())}.jsonl"
    with path.open("w", encoding="utf-8") as f:
        for msg in messages:
            f.write(json.dumps(msg, ensure_ascii=False, default=str) + "\n")
    return path


def summarize(messages: list[dict], focus: str | None = None) -> list[dict]:
    """Summarize messages via LLM and return a replacement message list."""
    transcript_path = _save_transcript(messages)
    print(f"[transcript saved: {transcript_path}]")

    conversation_text = json.dumps(messages, ensure_ascii=False, default=str)[-80000:]
    prompt = (
        "Summarize this conversation for continuity. Include: "
        "1) What was accomplished, 2) Current state, 3) Key decisions made. "
        "Be concise but preserve critical details."
    )
    if focus:
        prompt += f" Preserve this especially: {focus}."

    response = completion(
        model=os.getenv("MODEL_NAME"),
        messages=[{"role": "user", "content": f"{prompt}\n\n{conversation_text}"}],
    )
    summary = response.choices[0].message.content or "No summary generated."
    return [
        {
            "role": "user",
            "content": (
                f"[Conversation compressed. Transcript: {transcript_path}]\n\n"
                f"{summary}"
            ),
        }
    ]


def run(*, focus: str | None = None) -> str:
    """Placeholder — actual compression is handled by agent_loop."""
    return "Compressing conversation..."
