from pathlib import Path

from ..app_paths import current_workspace


TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "edit_file",
        "description": "Replace text in a file.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "File path to edit",
                },
                "old_text": {
                    "type": "string",
                    "description": "Existing text to replace",
                },
                "new_text": {
                    "type": "string",
                    "description": "Replacement text",
                },
            },
            "required": ["path", "old_text", "new_text"],
        },
    },
}


def run(*, path: str, old_text: str, new_text: str) -> str:
    try:
        file_path = Path(path).expanduser()
        if not file_path.is_absolute():
            file_path = current_workspace() / file_path
        if not file_path.exists():
            return f"Error: File not found: {path}"
        if not file_path.is_file():
            return f"Error: Not a file: {path}"

        content = file_path.read_text(encoding="utf-8")
        if old_text not in content:
            return f"Error: Text not found in {path}"

        file_path.write_text(content.replace(old_text, new_text, 1), encoding="utf-8")
        return f"Successfully edited {file_path}"
    except Exception as exc:
        return f"Error: edit_file failed: {exc}"
