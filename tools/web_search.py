from __future__ import annotations

import os

TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "web_search",
        "description": "Search the web and return titles, urls, and snippets.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query."},
                "count": {
                    "type": "integer",
                    "description": "Number of results (1-10).",
                    "minimum": 1,
                    "maximum": 10,
                },
            },
            "required": ["query"],
        },
    },
}


def run(*, query: str, count: int = 5) -> str:
    tavily_key = os.environ.get("TAVILY_API_KEY", "").strip()
    if not tavily_key:
        return "Error: TAVILY_API_KEY is not set."

    try:
        from tavily import TavilyClient

        client = TavilyClient(api_key=tavily_key)
        response = client.search(
            query=query,
            max_results=count,
            search_depth="basic",
            include_answer=False,
            include_raw_content=False,
        )
    except Exception as exc:  # noqa: BLE001
        return f"Error: web_search failed: {exc}"

    results = response.get("results", [])
    if not results:
        return f"No results for: {query}"

    lines = [f"Results for: {query}"]
    for i, item in enumerate(results[:count], 1):
        title = item.get("title", "")
        link = item.get("url", "")
        snippet = item.get("content", "")
        lines.append(f"{i}. {title}\n   {link}")
        if snippet:
            lines.append(f"   {snippet}")
    return "\n".join(lines)
