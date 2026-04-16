import json
import os
from pathlib import Path

from litellm import completion


WORKDIR = Path.cwd()
MAX_SUBAGENT_ITERATIONS = 30

TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "subagent",
        "description": (
            "Spawn a subagent with fresh context. It shares the filesystem "
            "but not conversation history."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "Task prompt for the subagent",
                },
                "description": {
                    "type": "string",
                    "description": "Short description of the delegated task",
                },
            },
            "required": ["prompt"],
        },
    },
}


def run(*, prompt: str, description: str = "subtask") -> str:
    print(f"> subagent ({description}):")
    print(prompt[:200])

    from . import TOOLS, TOOL_HANDLERS

    tool_name = TOOL_SCHEMA["function"]["name"]
    tools = [tool for tool in TOOLS if tool["function"]["name"] != tool_name]
    handlers = {
        name: handler
        for name, handler in TOOL_HANDLERS.items()
        if name != tool_name
    }
    messages = [
        {
            "role": "system",
            "content": (
                f"You are a coding subagent at {WORKDIR}. "
                "You have fresh context and do not know the parent conversation. "
                "Use tools as needed, then return a concise summary."
            ),
        },
        {"role": "user", "content": prompt},
    ]

    iterations = 0
    while True:
        if iterations >= MAX_SUBAGENT_ITERATIONS:
            return f"Error: Subagent exceeded {MAX_SUBAGENT_ITERATIONS} iterations"
        iterations += 1

        response = completion(
            model=os.getenv("MODEL_NAME") or os.getenv("LITELLM_MODEL"),
            messages=messages,
            tools=tools,
            tool_choice="auto",
        )

        choice = response.choices[0]
        assistant_message = choice.message.model_dump(exclude_none=True)
        messages.append(assistant_message)

        if choice.finish_reason != "tool_calls":
            return assistant_message["content"] or "(no summary)"

        for tool_call in assistant_message.get("tool_calls", []):
            tool_name = tool_call["function"]["name"]
            handler = handlers.get(tool_name)
            try:
                args = json.loads(tool_call["function"]["arguments"] or "{}")
            except json.JSONDecodeError:
                args = {}
            output = handler(**args) if handler else f"Unknown tool: {tool_name}"
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call["id"],
                    "content": output,
                }
            )
