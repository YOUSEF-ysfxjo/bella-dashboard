"""
Web client — fetch URLs and search the web.
Uses httpx for HTTP, DuckDuckGo for search (no API key required).
"""

from __future__ import annotations

import os
import re
from typing import Any

import httpx


def _fetch_max_chars() -> int:
    return max(2000, min(int(os.environ.get("BELLA_WEB_FETCH_MAX_CHARS", "20000")), 200_000))


_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; Bella/1.0; +https://github.com/YOUSEF-ysfxjo)"
}


class WebClient:
    def __init__(self, timeout: int = 20) -> None:
        self._timeout = timeout

    def fetch(self, url: str, as_text: bool = True) -> dict[str, Any]:
        """
        Fetch a URL. Returns status, content-type, and body.
        Strips HTML tags if content-type is text/html.
        """
        with httpx.Client(headers=_HEADERS, timeout=self._timeout, follow_redirects=True) as client:
            resp = client.get(url)

        content_type = resp.headers.get("content-type", "")
        body = resp.text if as_text else resp.content.decode("utf-8", errors="replace")

        if "text/html" in content_type:
            body = self._strip_html(body)

        cap = _fetch_max_chars()
        return {
            "url": str(resp.url),
            "status": resp.status_code,
            "content_type": content_type,
            "body": body[:cap],
            "truncated": len(body) > cap,
        }

    def search(self, query: str, max_results: int = 8) -> list[dict[str, Any]]:
        """
        Search the web using DuckDuckGo's HTML interface (no API key needed).
        Returns a list of {title, url, snippet} results.
        """
        try:
            from duckduckgo_search import DDGS
            with DDGS() as ddgs:
                results = list(ddgs.text(query, max_results=max_results))
            return [
                {
                    "title": r.get("title", ""),
                    "url": r.get("href", ""),
                    "snippet": r.get("body", ""),
                }
                for r in results
            ]
        except ImportError:
            # Fallback: DuckDuckGo HTML scrape
            return self._ddg_fallback(query, max_results)

    def _ddg_fallback(self, query: str, max_results: int) -> list[dict[str, Any]]:
        """Minimal DuckDuckGo HTML scrape fallback."""
        import urllib.parse
        q = urllib.parse.quote_plus(query)
        url = f"https://html.duckduckgo.com/html/?q={q}"
        try:
            result = self.fetch(url)
            # Return raw snippet as single result
            cap = min(2000, _fetch_max_chars())
            return [{"title": "Search results", "url": url, "snippet": result["body"][:cap]}]
        except Exception as e:
            return [{"error": str(e)}]

    @staticmethod
    def _strip_html(html: str) -> str:
        """Very basic HTML → plain text."""
        # Remove script/style blocks
        html = re.sub(r"<(script|style)[^>]*>.*?</(script|style)>", " ", html, flags=re.DOTALL | re.IGNORECASE)
        # Remove tags
        text = re.sub(r"<[^>]+>", " ", html)
        # Collapse whitespace
        text = re.sub(r"\s+", " ", text).strip()
        return text
