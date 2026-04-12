import json
import os
import subprocess
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from litellm import completion
from prompt_toolkit import PromptSession

load_dotenv()


def now() -> str:
    return datetime.now().astimezone().isoformat()


def create_session(model: str) -> tuple[dict, Path]:
    session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    session = {
        "session_id": session_id,
        "created_at": now(),
        "updated_at": now(),
        "model": model,
    }
    path = Path("logs/sessions") / f"{session_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return session, path


def save_session(session: dict, history: list[dict], path: Path) -> None:
    session["updated_at"] = now()
    path.write_text(
        json.dumps({**session, "history": history}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def run_bash(command: str) -> str:
    dangerous = ["rm -rf /", "sudo", "shutdown", "reboot", "> /dev/"]
    if any(item in command for item in dangerous):
        return "Error: Dangerous command blocked"

    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=120,
        )
        output = (result.stdout + result.stderr).strip()
        return output[:50000] if output else "(no output)"
    except subprocess.TimeoutExpired:
        return "Error: Timeout (120s)"


TOOL_HANDLERS = {
    "bash": lambda **kwargs: run_bash(kwargs["command"]),
}


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "bash",
            "description": "Run a shell command.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "Shell command to run",
                    }
                },
                "required": ["command"],
            },
        },
    }
]


def stream_assistant_message(messages: list[dict]) -> tuple[dict, str | None]:
    stream = completion(
        model=os.getenv("MODEL_NAME") or os.getenv("LITELLM_MODEL"),
        messages=messages,
        tools=TOOLS,
        tool_choice="auto",
        stream=True,
    )

    content_parts: list[str] = []
    tool_calls: dict[int, dict] = {}
    finish_reason = None

    for chunk in stream:
        choice = chunk.choices[0]
        finish_reason = choice.finish_reason or finish_reason
        delta = choice.delta

        text = delta.content or ""
        if text:
            content_parts.append(text)
            print(text, end="", flush=True)

        for tool_call in (delta.tool_calls or []):
            index = tool_call.index or 0
            call = tool_calls.setdefault(
                index,
                {
                    "id": "",
                    "type": "function",
                    "function": {"name": "", "arguments": ""},
                },
            )
            if tool_call.id:
                call["id"] = tool_call.id
            if tool_call.function:
                if tool_call.function.name:
                    call["function"]["name"] += tool_call.function.name
                if tool_call.function.arguments:
                    call["function"]["arguments"] += tool_call.function.arguments

    if content_parts:
        print()

    message = {"role": "assistant", "content": "".join(content_parts)}
    if tool_calls:
        message["tool_calls"] = [tool_calls[i] for i in sorted(tool_calls)]
    return message, finish_reason


def agent_loop(messages: list[dict]) -> str:
    while True:
        assistant_message, finish_reason = stream_assistant_message(messages)
        messages.append(assistant_message)
        save_session(session_meta, messages, session_path)

        if finish_reason != "tool_calls":
            return assistant_message["content"]

        for tool_call in assistant_message["tool_calls"]:
            tool_name = tool_call["function"]["name"]
            handler = TOOL_HANDLERS.get(tool_name)
            args = json.loads(tool_call["function"]["arguments"] or "{}")
            output = handler(**args) if handler else f"Unknown tool: {tool_name}"

            print(f"> {tool_name}:")
            print(output[:200])

            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call["id"],
                    "content": output
                }
            )
            save_session(session_meta, messages, session_path)


if __name__ == "__main__":
    model = os.getenv("MODEL_NAME")
    session_meta, session_path = create_session(model)
    history: list[dict] = []
    session = PromptSession()

    while True:
        query = session.prompt("You> ")
        if query in {"q", "quit", "exit"}:
            break

        history.append({"role": "user", "content": query})
        save_session(session_meta, history, session_path)
        agent_loop(history)
        print()
