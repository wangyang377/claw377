import json
from pathlib import Path
from typing import Any

from ..app_paths import tasks_dir


class TaskManager:
    def __init__(self, tasks_dir: Path):
        self.dir = tasks_dir
        self.dir.mkdir(parents=True, exist_ok=True)
        self._next_id = self._max_id() + 1

    def _max_id(self) -> int:
        ids = [int(f.stem.split("_")[1]) for f in self.dir.glob("task_*.json")]
        return max(ids) if ids else 0

    def _path(self, task_id: int) -> Path:
        return self.dir / f"task_{task_id}.json"

    def _load(self, task_id: int) -> dict[str, Any]:
        path = self._path(task_id)
        if not path.exists():
            raise ValueError(f"Task {task_id} not found")
        return json.loads(path.read_text(encoding="utf-8"))

    def _save(self, task: dict[str, Any]) -> None:
        self._path(task["id"]).write_text(
            json.dumps(task, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def create(self, subject: str, description: str = "", owner: str = "") -> str:
        task = {
            "id": self._next_id,
            "subject": subject,
            "description": description,
            "status": "pending",
            "blockedBy": [],
            "owner": owner,
        }
        self._save(task)
        self._next_id += 1
        return json.dumps(task, indent=2, ensure_ascii=False)

    def get(self, task_id: int) -> str:
        return json.dumps(self._load(task_id), indent=2, ensure_ascii=False)

    def update(
        self,
        task_id: int,
        status: str | None = None,
        addBlockedBy: list[int] | None = None,
        removeBlockedBy: list[int] | None = None,
        owner: str | None = None,
    ) -> str:
        task = self._load(task_id)
        if status is not None:
            if status not in ("pending", "in_progress", "completed"):
                raise ValueError(f"Invalid status: {status}")
            task["status"] = status
            if status == "completed":
                self._clear_dependency(task_id)
        if addBlockedBy:
            task["blockedBy"] = sorted(set(task.get("blockedBy", []) + addBlockedBy))
        if removeBlockedBy:
            task["blockedBy"] = [x for x in task.get("blockedBy", []) if x not in removeBlockedBy]
        if owner is not None:
            task["owner"] = owner
        self._save(task)
        return json.dumps(task, indent=2, ensure_ascii=False)

    def _clear_dependency(self, completed_id: int) -> None:
        for task_file in self.dir.glob("task_*.json"):
            task = json.loads(task_file.read_text(encoding="utf-8"))
            blocked_by = task.get("blockedBy", [])
            if completed_id not in blocked_by:
                continue
            task["blockedBy"] = [x for x in blocked_by if x != completed_id]
            self._save(task)

    def list_all(self) -> str:
        tasks = []
        files = sorted(self.dir.glob("task_*.json"), key=lambda f: int(f.stem.split("_")[1]))
        for task_file in files:
            tasks.append(json.loads(task_file.read_text(encoding="utf-8")))
        if not tasks:
            return "No tasks."

        lines = []
        for task in tasks:
            marker = {
                "pending": "[ ]",
                "in_progress": "[>]",
                "completed": "[x]",
            }.get(task["status"], "[?]")
            blocked = f" (blocked by: {task['blockedBy']})" if task.get("blockedBy") else ""
            owner = f" owner={task['owner']}" if task.get("owner") else ""
            lines.append(f"{marker} #{task['id']}: {task['subject']}{blocked}{owner}")
        return "\n".join(lines)


def _tasks() -> TaskManager:
    return TaskManager(tasks_dir())


TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "task_create",
            "description": "Create a persistent task stored in the workspace task state.",
            "parameters": {
                "type": "object",
                "properties": {
                    "subject": {"type": "string", "description": "Short task title"},
                    "description": {"type": "string", "description": "Optional task details"},
                    "owner": {"type": "string", "description": "Optional task owner"},
                },
                "required": ["subject"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "task_update",
            "description": "Update a persistent task's status, owner, or dependencies.",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_id": {"type": "integer", "description": "Task ID"},
                    "status": {
                        "type": "string",
                        "enum": ["pending", "in_progress", "completed"],
                        "description": "New task status",
                    },
                    "addBlockedBy": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "Task IDs to add as blockers",
                    },
                    "removeBlockedBy": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "Task IDs to remove from blockers",
                    },
                    "owner": {"type": "string", "description": "Optional task owner"},
                },
                "required": ["task_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "task_list",
            "description": "List all persistent tasks.",
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "task_get",
            "description": "Get a persistent task by ID.",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_id": {"type": "integer", "description": "Task ID"},
                },
                "required": ["task_id"],
            },
        },
    },
]


TOOL_HANDLERS = {
    "task_create": lambda **kw: _tasks().create(
        kw["subject"],
        kw.get("description", ""),
        kw.get("owner", ""),
    ),
    "task_update": lambda **kw: _tasks().update(
        kw["task_id"],
        kw.get("status"),
        kw.get("addBlockedBy"),
        kw.get("removeBlockedBy"),
        kw.get("owner"),
    ),
    "task_list": lambda **kw: _tasks().list_all(),
    "task_get": lambda **kw: _tasks().get(kw["task_id"]),
}
