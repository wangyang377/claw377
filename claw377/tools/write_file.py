from pathlib import Path

from ..app_paths import current_workspace


TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "write_file",
        "description": "Write text content to a file.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "File path to write",
                },
                "content": {
                    "type": "string",
                    "description": "Text content to write",
                },
            },
            "required": ["path", "content"],
        },
    },
}


def run(*, path: str, content: str) -> str:
    try:
        file_path = Path(path).expanduser()
        if not file_path.is_absolute():
            file_path = current_workspace() / file_path
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")
        return f"Successfully wrote {len(content)} characters to {file_path}"
    except Exception as exc:
        return f"Error: write_file failed: {exc}"
