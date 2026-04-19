from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

from litellm import completion
from prompt_toolkit import PromptSession

from .app_paths import (
    app_home,
    config_env_path,
    current_workspace,
    environment_status,
    load_environment,
    sessions_dir,
)
from .consolidator import Consolidator
from .context import build_system_prompt, default_memory_text
from .memory_store import MemoryStore
from .memory_writer import LongTermMemoryWriter
from .session import Session
from .tools import TOOLS, TOOL_HANDLERS
from .tools.background import BG

MICRO_COMPACT_KEEP_RECENT = 3
MICRO_COMPACT_MIN_CHARS = 200
PRESERVE_RESULT_TOOLS = {"read_file"}
AUTO_COMPACT_THRESHOLD = 50000
VERSION = "0.1.0"
session_meta: dict | None = None
session_path: Path | None = None
memory_store: MemoryStore | None = None
consolidator: Consolidator | None = None
memory_writer: LongTermMemoryWriter | None = None


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
        "workspace": str(current_workspace()),
    }
    path = sessions_dir() / f"{session_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return session, path


def session_path_for(session_id: str) -> Path:
    return sessions_dir() / f"{session_id}.json"


def current_system_prompt(recent_archive_summary: str = "") -> str:
    if memory_store is None:
        raise RuntimeError("Memory store is not initialized")
    return build_system_prompt(
        memory_text=memory_store.read_memory(),
        recent_archive_summary=recent_archive_summary,
    )


def save_session(session: dict, runtime_session: Session, path: Path) -> None:
    session["updated_at"] = now()
    path.write_text(
        json.dumps(
            {
                **session,
                "system_prompt": current_system_prompt(
                    runtime_session.recent_archive_summary
                ),
                "last_consolidated": runtime_session.last_consolidated,
                "recent_archive_summary": runtime_session.recent_archive_summary,
                "history": runtime_session.messages,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def load_session(session_id: str) -> tuple[dict, Session, Path]:
    path = session_path_for(session_id)
    payload = json.loads(path.read_text(encoding="utf-8"))
    runtime_session = Session(
        messages=payload.get("history", []),
        last_consolidated=payload.get("last_consolidated", 0),
        recent_archive_summary=payload.get("recent_archive_summary", ""),
    )
    session = {
        "session_id": payload["session_id"],
        "created_at": payload.get("created_at", now()),
        "updated_at": payload.get("updated_at", now()),
        "model": payload.get("model", "unknown-model"),
        "workspace": payload.get("workspace", str(current_workspace())),
    }
    return session, runtime_session, path


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


def build_prompt_messages(
    messages: list[dict],
    *,
    recent_archive_summary: str = "",
    current_message: str | None = None,
) -> list[dict]:
    if memory_store is None:
        raise RuntimeError("Memory store is not initialized")
    prompt_messages = list(messages)
    if current_message:
        prompt_messages.append(
            {"role": "user", "content": f"{runtime_context()}\n\n{current_message}"}
        )
    return [
        {
            "role": "system",
            "content": current_system_prompt(recent_archive_summary),
        },
        *prompt_messages,
    ]


def stream_assistant_message(
    messages: list[dict],
    *,
    recent_archive_summary: str = "",
) -> tuple[dict, str | None]:
    stream = completion(
        model=os.getenv("MODEL_NAME") or os.getenv("LITELLM_MODEL"),
        messages=build_prompt_messages(
            messages,
            recent_archive_summary=recent_archive_summary,
        ),
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


def agent_loop(runtime_session: Session) -> str:
    if (
        session_meta is None
        or session_path is None
        or consolidator is None
        or memory_writer is None
    ):
        raise RuntimeError("Session is not initialized")
    while True:
        # Drain background task notifications
        notifs = BG.drain_notifications()
        if notifs:
            notif_text = "\n".join(
                f"[bg:{n['task_id']}] {n['status']}: {n['result']}" for n in notifs
            )
            runtime_session.add(
                {
                    "role": "user",
                    "content": f"<background-results>\n{notif_text}\n</background-results>",
                }
            )

        micro_compact(runtime_session.active_messages())
        if consolidator.maybe_consolidate(
            runtime_session,
            build_prompt_messages=build_prompt_messages,
        ):
            print("[consolidated old messages]")
            if memory_writer.maybe_update():
                print("[updated long-term memory]")
            save_session(session_meta, runtime_session, session_path)

        assistant_message, finish_reason = stream_assistant_message(
            runtime_session.active_messages(),
            recent_archive_summary=runtime_session.recent_archive_summary,
        )
        runtime_session.add(assistant_message)
        save_session(session_meta, runtime_session, session_path)

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
                output = "Consolidating old conversation context..."
            else:
                handler = TOOL_HANDLERS.get(tool_name)
                output = handler(**args) if handler else f"Unknown tool: {tool_name}"

            print(f"> {tool_name}:")
            print(output[:200])

            runtime_session.add(
                {
                    "role": "tool",
                    "tool_call_id": tool_call["id"],
                    "name": tool_name,
                    "content": output,
                }
            )
            save_session(session_meta, runtime_session, session_path)

        if manual_compact:
            print("[manual consolidate]")
            if consolidator.maybe_consolidate(
                runtime_session,
                build_prompt_messages=build_prompt_messages,
            ):
                if compact_focus:
                    runtime_session.recent_archive_summary = (
                        f"{runtime_session.recent_archive_summary}\n\nFocus: {compact_focus}".strip()
                    )
                if memory_writer.maybe_update():
                    print("[updated long-term memory]")
                save_session(session_meta, runtime_session, session_path)


def _print_startup_help(missing: list[str]) -> None:
    print("claw377 is not configured yet.", file=sys.stderr)
    print(f"Config file: {config_env_path()}", file=sys.stderr)
    print(f"Workspace:   {current_workspace()}", file=sys.stderr)
    print("", file=sys.stderr)
    print("Missing:", file=sys.stderr)
    for item in missing:
        print(f"- {item}", file=sys.stderr)
    print("", file=sys.stderr)
    print("Fill in the config file above, or create a local .env in your workspace.", file=sys.stderr)


def _resume_session(session_id: str) -> tuple[dict, Session, Path] | None:
    try:
        return load_session(session_id)
    except FileNotFoundError:
        print(f"Session not found: {session_id}")
    except json.JSONDecodeError:
        print(f"Session is not readable: {session_id}")
    return None


def _handle_frontend_command(command: str) -> tuple[str, tuple[dict, Session, Path] | None]:
    if not command.startswith("/"):
        return "continue", None

    parts = command.split(maxsplit=1)
    name = parts[0]
    arg = parts[1].strip() if len(parts) > 1 else ""

    if name == "/resume":
        if not arg:
            print("Usage: /resume <session_id>")
            return "handled", None
        return "resume", _resume_session(arg)

    print(f"Unknown command: {name}")
    return "handled", None


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="claw377 terminal agent")
    parser.add_argument("prompt", nargs="?", help="Run one prompt and exit.")
    parser.add_argument("--version", action="store_true", help="Print version and exit.")
    parser.add_argument("--print-paths", action="store_true", help="Print data/config paths and exit.")
    return parser.parse_args(argv)


def _print_paths() -> None:
    print(f"app_home={app_home()}")
    print(f"config={config_env_path()}")
    print(f"sessions={sessions_dir()}")
    from .app_paths import memory_dir, tasks_dir, transcripts_dir

    print(f"transcripts={transcripts_dir()}")
    print(f"workspace_tasks={tasks_dir()}")
    print(f"workspace_memory={memory_dir()}")


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if args.version:
        print(f"claw377 {VERSION}")
        return 0

    load_environment()

    if args.print_paths:
        _print_paths()
        return 0

    ok, missing = environment_status()
    if not ok:
        _print_startup_help(missing)
        return 1

    model = os.getenv("MODEL_NAME") or os.getenv("LITELLM_MODEL") or "unknown-model"
    global session_meta, session_path, memory_store, consolidator, memory_writer
    session_meta, session_path = create_session(model)
    runtime_session = Session()
    memory_store = MemoryStore()
    memory_store.ensure_memory_file(default_memory_text())
    consolidator = Consolidator(memory_store, AUTO_COMPACT_THRESHOLD)
    memory_writer = LongTermMemoryWriter(memory_store)

    if args.prompt:
        runtime_session.add({"role": "user", "content": f"{runtime_context()}\n\n{args.prompt}"})
        save_session(session_meta, runtime_session, session_path)
        agent_loop(runtime_session)
        print()
        return 0

    if not sys.stdin.isatty():
        print("Interactive mode requires a TTY. Pass a prompt argument for one-shot mode.", file=sys.stderr)
        return 1

    print(f"claw377 [{model}]")
    print(f"workspace: {current_workspace()}")
    print(f"session log: {session_path}")
    print("Type 'exit' to quit. Use /resume <session_id> to restore a saved session.")

    session = PromptSession()
    while True:
        query = session.prompt("You> ").strip()
        if not query:
            continue
        if query in {"q", "quit", "exit"}:
            break
        action, payload = _handle_frontend_command(query)
        if action == "handled":
            continue
        if action == "resume":
            if payload is None:
                continue
            session_meta, runtime_session, session_path = payload
            print(f"[resumed {session_meta['session_id']}]")
            print(f"session log: {session_path}")
            continue

        runtime_session.add({"role": "user", "content": f"{runtime_context()}\n\n{query}"})
        save_session(session_meta, runtime_session, session_path)
        agent_loop(runtime_session)
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
