"""
Web MCP tools — fetch URLs and search the web.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from fastmcp import FastMCP
    from clients.web import WebClient


def _web_search_defaults() -> tuple[int, int]:
    """(default max_results per call, hard ceiling)."""
    default = int(os.environ.get("BELLA_WEB_SEARCH_DEFAULT_RESULTS", "4"))
    hard = int(os.environ.get("BELLA_WEB_SEARCH_MAX_RESULTS", "10"))
    default = max(1, min(default, hard))
    hard = max(default, min(hard, 20))
    return default, hard


def register(mcp: "FastMCP", web: "WebClient") -> None:

    @mcp.tool()
    def web_fetch(url: str) -> dict[str, Any]:
        """
        Fetch a URL and return its content as plain text.
        HTML pages are automatically stripped of tags.
        Body length cap: env `BELLA_WEB_FETCH_MAX_CHARS` (default 20000, max 200000).

        Prefer **one** targeted fetch after a narrow web_search (or a URL Yousef gave).
        Do not fetch large pages speculatively.

        Example: web_fetch("https://arxiv.org/abs/2310.06825")
        """
        return web.fetch(url)

    @mcp.tool()
    def web_search(query: str, max_results: int | None = None) -> list[dict[str, Any]]:
        """
        Web search (DuckDuckGo). **Use last** after wiki, Obsidian, Notion, and GitHub — it is the noisiest and most token-heavy.

        Defaults are intentionally small (env `BELLA_WEB_SEARCH_DEFAULT_RESULTS`, default 4).
        Hard cap: `BELLA_WEB_SEARCH_MAX_RESULTS` (default 10, max 20).

        Use **one precise query**; avoid firing several vague searches in parallel.
        """
        default_n, hard_n = _web_search_defaults()
        n = default_n if max_results is None else max_results
        n = max(1, min(int(n), hard_n))
        return web.search(query, max_results=n)
