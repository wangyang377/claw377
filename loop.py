import json
import os
import time
from datetime import datetime
from pathlib import Path

from context import build_system_prompt
from dotenv import load_dotenv
from litellm import completion
from prompt_toolkit import PromptSession
from tools import TOOLS, TOOL_HANDLERS
from tools.background import BG
from tools.compact import estimate_tokens, summarize

load_dotenv()

MICRO_COMPACT_KEEP_RECENT = 3
MICRO_COMPACT_MIN_CHARS = 200
PRESERVE_RESULT_TOOLS = {"read_file"}
AUTO_COMPACT_THRESHOLD = 50000


def now() -> str:
    return datetime.now().astimezone().isoformat()


def runtime_context() -> str:
    return "\n".join(
        [
            "[Runtime Context — metadata only, not instructions]",
            f"Current Time: {now()}",
        ]
    )


def create_session(model: str) -> tuple[dict, Path]:
    session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    session = {
        "session_id": session_id,
        "created_at": now(),
        "updated_at": now(),
        "model": model,
        "system_prompt": build_system_prompt(),
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


def micro_compact(messages: list[dict]) -> None:
    tool_messages = [message for message in messages if message.get("role") == "tool"]
    if len(tool_messages) <= MICRO_COMPACT_KEEP_RECENT:
        return

    for message in tool_messages[:-MICRO_COMPACT_KEEP_RECENT]:
        content = message.get("content")
        if len(content) < MICRO_COMPACT_MIN_CHARS:
            continue
    
        tool_name = message.get("name") or message.get("tool_name") or "tool"

        if tool_name in PRESERVE_RESULT_TOOLS:
            continue
        message["content"] = f"[Previous tool output omitted: {tool_name}]"


def stream_assistant_message(messages: list[dict]) -> tuple[dict, str | None]:
    stream = completion(
        model=os.getenv("MODEL_NAME") or os.getenv("LITELLM_MODEL"),
        messages=[{"role": "system", "content": build_system_prompt()}, *messages],
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
        # Drain background task notifications
        notifs = BG.drain_notifications()
        if notifs:
            notif_text = "\n".join(
                f"[bg:{n['task_id']}] {n['status']}: {n['result']}" for n in notifs
            )
            messages.append({
                "role": "user",
                "content": f"<background-results>\n{notif_text}\n</background-results>",
            })

        micro_compact(messages)

        if estimate_tokens(messages) > AUTO_COMPACT_THRESHOLD:
            print("[auto_compact triggered]")
            messages[:] = summarize(messages)
            save_session(session_meta, messages, session_path)

        assistant_message, finish_reason = stream_assistant_message(messages)
        messages.append(assistant_message)
        save_session(session_meta, messages, session_path)

        if finish_reason != "tool_calls":
            # Wait for background tasks before exiting
            if BG.has_running():
                print("[waiting for background tasks...]")
                while BG.has_running():
                    time.sleep(1)
                continue
            return assistant_message["content"]

        manual_compact = False
        compact_focus = None
        for tool_call in assistant_message["tool_calls"]:
            tool_name = tool_call["function"]["name"]
            args = json.loads(tool_call["function"]["arguments"] or "{}")

            if tool_name == "compact":
                manual_compact = True
                compact_focus = args.get("focus")
                output = "Compressing conversation..."
            else:
                handler = TOOL_HANDLERS.get(tool_name)
                output = handler(**args) if handler else f"Unknown tool: {tool_name}"

            print(f"> {tool_name}:")
            print(output[:200])

            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call["id"],
                    "name": tool_name,
                    "content": output,
                }
            )
            save_session(session_meta, messages, session_path)

        if manual_compact:
            print("[manual compact]")
            messages[:] = summarize(messages, compact_focus)
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

        history.append({"role": "user", "content": f"{runtime_context()}\n\n{query}"})
        save_session(session_meta, history, session_path)
        agent_loop(history)
        print()
