"""Background task execution — fire and forget, drain before each LLM call."""

import subprocess
import threading
import uuid
from pathlib import Path

WORKDIR = Path.cwd()


class BackgroundManager:
    def __init__(self):
        self.tasks: dict[str, dict] = {}
        self._notifications: list[dict] = []
        self._lock = threading.Lock()

    def run(self, command: str) -> str:
        task_id = str(uuid.uuid4())[:8]
        self.tasks[task_id] = {"status": "running", "result": None, "command": command}
        thread = threading.Thread(target=self._execute, args=(task_id, command), daemon=True)
        thread.start()
        return f"Background task {task_id} started: {command[:80]}"

    def _execute(self, task_id: str, command: str) -> None:
        try:
            r = subprocess.run(
                command, shell=True, cwd=WORKDIR,
                capture_output=True, text=True, timeout=300,
            )
            output = (r.stdout + r.stderr).strip()[:50000]
            status = "completed"
        except subprocess.TimeoutExpired:
            output = "Error: Timeout (300s)"
            status = "timeout"
        except Exception as e:
            output = f"Error: {e}"
            status = "error"

        self.tasks[task_id]["result"] = output or "(no output)"
        with self._lock:
            self._notifications.append({
                "task_id": task_id,
                "status": status,
                "command": command[:80],
                "result": (output or "(no output)")[:500],
            })
        self.tasks[task_id]["status"] = status

    def check(self, task_id: str | None = None) -> str:
        if task_id:
            t = self.tasks.get(task_id)
            if not t:
                return f"Error: Unknown task {task_id}"
            return f"[{t['status']}] {t['command'][:60]}\n{t.get('result') or '(running)'}"
        lines = [f"{tid}: [{t['status']}] {t['command'][:60]}" for tid, t in self.tasks.items()]
        return "\n".join(lines) if lines else "No background tasks."

    def drain_notifications(self) -> list[dict]:
        with self._lock:
            notifs = list(self._notifications)
            self._notifications.clear()
        return notifs

    def has_running(self) -> bool:
        return any(t["status"] == "running" for t in self.tasks.values())


BG = BackgroundManager()

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "background_run",
            "description": "Run a command in the background. Returns task_id immediately without blocking.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "Shell command to run"},
                },
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_background",
            "description": "Check background task status. Omit task_id to list all tasks.",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_id": {"type": "string", "description": "Task ID to check"},
                },
            },
        },
    },
]

TOOL_HANDLERS = {
    "background_run": lambda **kw: BG.run(kw["command"]),
    "check_background": lambda **kw: BG.check(kw.get("task_id")),
}