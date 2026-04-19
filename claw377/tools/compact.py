"""Compact tool — lets the model trigger conversation consolidation."""

import json

TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "compact",
        "description": (
            "Consolidate older conversation context when the session is getting too long "
            "or before starting a new major task."
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


def run(*, focus: str | None = None) -> str:
    if focus:
        return f"Consolidating conversation context with focus: {focus}"
    return "Consolidating conversation context..."
