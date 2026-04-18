from __future__ import annotations

import re
from html import unescape
from urllib.parse import urlparse
from urllib.request import Request, urlopen

TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "web_fetch",
        "description": "Fetch a web page and return readable text content.",
        "parameters": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "Target URL (http/https)."},
                "max_chars": {
                    "type": "integer",
                    "description": "Max returned chars.",
                    "minimum": 200,
                },
            },
            "required": ["url"],
        },
    },
}


def _is_valid_url(url: str) -> bool:
    p = urlparse(url)
    return p.scheme in ("http", "https") and bool(p.netloc)


def _html_to_text(html: str) -> str:
    text = re.sub(r"<script[\s\S]*?</script>", "", html, flags=re.I)
    text = re.sub(r"<style[\s\S]*?</style>", "", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = unescape(text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def run(*, url: str, max_chars: int = 12000) -> str:
    if not _is_valid_url(url):
        return f"Error: invalid url: {url}"

    req = Request(
        url=url,
        headers={"User-Agent": "mynanobot/0.1"},
        method="GET",
    )

    try:
        with urlopen(req, timeout=20) as resp:
            ctype = (resp.headers.get("content-type", "") or "").lower()
            body = resp.read().decode("utf-8", errors="replace")
    except Exception as exc:  # noqa: BLE001
        return f"Error: web_fetch failed: {exc}"

    text = _html_to_text(body) if "html" in ctype else body
    if len(text) > max_chars:
        text = text[:max_chars] + "\n... (truncated)"
    return text
