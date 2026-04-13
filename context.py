import platform
from datetime import datetime
from pathlib import Path
import re
from typing import Optional, Tuple


WORKSPACE = Path(__file__).resolve().parent
BOOTSTRAP_DIR = WORKSPACE / "bootstrap"
BOOTSTRAP_FILES = ["AGENTS.md", "SOUL.md", "USER.md", "TOOLS.md"]


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
        content = _strip_title(_read_text(BOOTSTRAP_DIR / name))
        if content:
            parts.append(f"## {name}\n{content}")
    if parts:
        return "# Workspace Bootstrap\n\n" + "\n\n".join(parts)
    return ""


def _memory_section() -> str:
    content = _strip_title(_read_text(WORKSPACE / "memory" / "MEMORY.md"))
    if content:
        return f"# Memory\n\n{content}"
    return ""



def _list_skills() -> list[dict[str, str]]:
    skills_root = WORKSPACE / "skills"
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


def _base_system_prompt() -> str:
    parts = [
        _identity_section(),
        _bootstrap_section(),
        _memory_section(),
    ]
    return "\n\n---\n\n".join(part for part in parts if part)


def build_system_prompt() -> str:
    system_prompt = _base_system_prompt()
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
        "You have access to the following skills.",
        "A skill description is the primary trigger signal for when to use it.",
        "If a skill is relevant, inspect its SKILL.md with shell tools before acting.",
        "",
        "Available skills:",
    ]
    for skill in skills:
        lines.append(f"- {skill['name']}: {skill['description']} ({skill['path']})")
    lines.extend(
        [
            "",
            "Execution rules:",
            "- Prefer completing the task over only describing how it could be done.",
            "- When a task matches a skill, inspect its SKILL.md with shell tools such as cat, sed, or rg, then execute the required tools.",
            "- Never read skill scripts unless you need to modify them.",
            "- If a task is clearly programmable but not easy to complete directly, check whether the programmer skill applies before saying the task cannot be done.",
        ]
    )
    return "\n".join(lines)
