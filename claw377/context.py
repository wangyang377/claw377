import platform
from datetime import datetime
from pathlib import Path
import re
from typing import Optional, Tuple


PACKAGE_ROOT = Path(__file__).resolve().parent
WORKSPACE = PACKAGE_ROOT.parent.resolve()
TEMPLATES_DIR = PACKAGE_ROOT / "templates"
BOOTSTRAP_FILES = ["AGENTS.md", "SOUL.md", "USER.md", "TOOLS.md"]
BOOTSTRAP_TITLES = {
    "AGENTS.md": "Agent Operating Principles",
    "SOUL.md": "Agent Style",
    "USER.md": "User Preferences",
    "TOOLS.md": "Tool Rules",
}


def _read_text(path: Path) -> str:
    if not path.exists() or not path.is_file():
        return ""
    return path.read_text(encoding="utf-8").strip()


def _strip_title(text: str) -> str:
    lines = text.splitlines()
    if lines and lines[0].startswith("# "):
        return "\n".join(lines[1:]).strip()
    return text


def _parse_skill_metadata(path: Path) -> Optional[Tuple[str, str]]:
    text = _read_text(path)
    if not text.startswith("---"):
        return None

    match = re.match(r"^---\n(.*?)\n---(?:\n|$)", text, re.DOTALL)
    if not match:
        return None

    metadata: dict[str, str] = {}
    for line in match.group(1).splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        metadata[key.strip()] = value.strip().strip('"').strip("'")

    name = metadata.get("name", "").strip()
    description = metadata.get("description", "").strip()
    if not name:
        return None
    return name, description


def _platform_policy() -> str:
    system = platform.system()
    if system == "Windows":
        lines = [
            "# Platform Policy",
            "- You are running on Windows.",
            "- Prefer UTF-8 text handling where possible.",
            "- Be careful with shell syntax and path separators.",
        ]
    else:
        lines = [
            "# Platform Policy",
            "- You are running on a POSIX system.",
            "- Prefer UTF-8 text and standard shell tools.",
            "- Prefer forward-slash paths and explicit command arguments.",
        ]
    return "\n".join(lines)


def _identity_section() -> str:
    lines = [
        "# Identity And Runtime",
        "Agent: Claw",
        "You are the primary coding agent for this workspace.",
        "",
        "## Runtime",
        f"- Workspace: {WORKSPACE}",
        f"- OS: {platform.system()} {platform.machine()}",
        f"- Python: {platform.python_version()}",
        "",
        _platform_policy(),
    ]
    return "\n".join(lines)


def _bootstrap_section() -> str:
    parts = []
    for name in BOOTSTRAP_FILES:
        content = _strip_title(_read_text(TEMPLATES_DIR / name))
        if content:
            title = BOOTSTRAP_TITLES.get(name, name)
            parts.append(f"## {title}\n{content}")
    if parts:
        return "# Workspace Bootstrap\n\n" + "\n\n".join(parts)
    return ""


def default_memory_text() -> str:
    return _read_text(TEMPLATES_DIR / "memory" / "MEMORY.md")


def _memory_section(memory_text: str | None = None) -> str:
    content = _strip_title(memory_text if memory_text is not None else default_memory_text())
    if content:
        return f"# Memory\n\n{content}"
    return ""


def _recent_archive_section(summary: str | None = None) -> str:
    content = (summary or "").strip()
    if content:
        return f"# Recent Archive Summary\n\n{content}"
    return ""


def _escape_xml(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )


def _format_skills_for_prompt(skills: list[dict[str, str]]) -> str:
    if not skills:
        return ""

    lines = [
        "The following skills provide specialized instructions for specific tasks.",
        "Use read_file to load a skill's SKILL.md when the task clearly matches its description.",
        "When a skill file references a relative path, resolve it against the skill directory.",
        "",
        "<available_skills>",
    ]
    for skill in skills:
        lines.append("  <skill>")
        lines.append(f"    <name>{_escape_xml(skill['name'])}</name>")
        lines.append(f"    <description>{_escape_xml(skill['description'])}</description>")
        lines.append(f"    <location>{_escape_xml(skill['path'])}</location>")
        lines.append("  </skill>")
    lines.append("</available_skills>")
    return "\n".join(lines)



def _list_skills() -> list[dict[str, str]]:
    skills_root = PACKAGE_ROOT / "skills"
    if not skills_root.exists():
        return []

    skills: list[dict[str, str]] = []
    for path in sorted(skills_root.glob("*/SKILL.md")):
        if not path.is_file():
            continue
        metadata = _parse_skill_metadata(path)
        if metadata is None:
            continue
        name, description = metadata
        skills.append(
            {
                "name": name,
                "description": description,
                "path": str(path),
            }
        )
    return skills


def _base_system_prompt(
    *,
    memory_text: str | None = None,
    recent_archive_summary: str | None = None,
) -> str:
    parts = [
        _identity_section(),
        _bootstrap_section(),
        _memory_section(memory_text),
        _recent_archive_section(recent_archive_summary),
    ]
    return "\n\n---\n\n".join(part for part in parts if part)


def build_system_prompt(
    *,
    memory_text: str | None = None,
    recent_archive_summary: str | None = None,
) -> str:
    system_prompt = _base_system_prompt(
        memory_text=memory_text,
        recent_archive_summary=recent_archive_summary,
    )
    now = datetime.now().astimezone()
    today = now.strftime("%Y-%m-%d")
    timezone_name = now.tzname() or "local timezone"
    skills = _list_skills()
    date_rules = [
        "",
        "# Date handling rules:",
        f"- Current local date is {today} ({timezone_name}).",
        "- For date mentions without a year (e.g. '3月1号'), default to the current year.",
        "- Before running date-sensitive tools, convert dates to explicit YYYY-MM-DD.",
    ]
    if not skills:
        return "\n".join([system_prompt, *date_rules])

    lines = [
        system_prompt,
        *date_rules,
        "",
        "## Skills",
        "Before replying: scan <available_skills> <description> entries.",
        "- If exactly one skill clearly applies: read its SKILL.md at <location> with `read_file`, then follow it.",
        "- If multiple skills could apply: choose the most specific one, then read and follow it.",
        "- If no skill clearly applies: do not read any SKILL.md.",
        "- Read at most one skill up front; only fall back to generic tools if that skill is insufficient or fails.",
        "",
        _format_skills_for_prompt(skills),
    ]
    lines.extend(
        [
            "",
            "Execution rules:",
            "- Prefer completing the task over only describing how it could be done.",
            "- If a user request can be handled by a relevant skill, prefer that skill over generic tools.",
            "- Do not use web_search first when an existing skill already covers the task.",
            "- Never read skill scripts unless you need to modify them.",
        ]
    )
    return "\n".join(lines)
