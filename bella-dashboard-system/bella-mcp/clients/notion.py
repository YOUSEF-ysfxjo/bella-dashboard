"""
Notion API client — full surface access.
Wraps the official notion-client SDK.
All methods return raw API responses (dicts) — tools layer handles formatting.
"""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

import httpx
from notion_client import Client
from notion_client.errors import APIResponseError

_NOTION_API_BASE = "https://api.notion.com/v1"
_NOTION_VERSION = "2022-06-28"


def _notion_http_timeout() -> httpx.Timeout:
    """Long read timeout: recursive page fetches issue many sequential API calls."""
    read = float(os.environ.get("NOTION_HTTP_READ_TIMEOUT", "180"))
    return httpx.Timeout(connect=30.0, read=read, write=30.0, pool=30.0)


def _paginate_block_children(client: Client, block_id: str) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    cursor: str | None = None
    while True:
        kwargs: dict[str, Any] = {"block_id": block_id, "page_size": 100}
        if cursor:
            kwargs["start_cursor"] = cursor
        resp = client.blocks.children.list(**kwargs)
        results.extend(resp.get("results", []))
        if not resp.get("has_more"):
            break
        cursor = resp.get("next_cursor")
    return results


def _recursive_fill_subtree(
    client: Client,
    block_id: str,
    depth: int,
    max_depth: int,
) -> list[dict[str, Any]]:
    """Depth-first fetch using one httpx client (safe for a single thread)."""
    try:
        blocks = _paginate_block_children(client, block_id)
    except APIResponseError as e:
        return [{"type": "_error", "id": block_id, "_access_error": str(e)}]
    if depth >= max_depth:
        return blocks
    for block in blocks:
        if block.get("has_children"):
            try:
                block["children"] = _recursive_fill_subtree(
                    client, block["id"], depth + 1, max_depth
                )
            except APIResponseError as e:
                block["children"] = []
                block["_access_error"] = str(e)
    return blocks


class NotionClient:
    def __init__(self) -> None:
        api_key = os.environ.get("NOTION_API_KEY", "")
        if not api_key:
            raise RuntimeError("NOTION_API_KEY is not set")
        self._http_timeout = _notion_http_timeout()
        self._client = Client(
            auth=api_key,
            client=httpx.Client(timeout=self._http_timeout),
        )
        self._api_key = api_key
        self._headers = {
            "Authorization": f"Bearer {api_key}",
            "Notion-Version": _NOTION_VERSION,
            "Content-Type": "application/json",
        }

    # ──────────────────────────────────────────────
    # Pages
    # ──────────────────────────────────────────────

    def get_page(self, page_id: str) -> dict[str, Any]:
        """Retrieve page metadata and properties."""
        return self._client.pages.retrieve(page_id=page_id)

    def create_page(
        self,
        parent_id: str,
        title: str,
        properties: dict[str, Any] | None = None,
        children: list[dict[str, Any]] | None = None,
        is_database_entry: bool = False,
    ) -> dict[str, Any]:
        """
        Create a page.
        - If parent is a database, set is_database_entry=True.
        - properties should follow Notion property value schema.
        - children is a list of block objects to pre-populate content.
        """
        if is_database_entry:
            parent = {"database_id": parent_id}
        else:
            parent = {"page_id": parent_id}

        payload: dict[str, Any] = {"parent": parent}

        # Title property — works for both pages and database entries
        base_props: dict[str, Any] = {
            "title": {"title": [{"text": {"content": title}}]}
        }
        if properties:
            base_props.update(properties)
        payload["properties"] = base_props

        if children:
            payload["children"] = children

        return self._client.pages.create(**payload)

    def update_page(
        self,
        page_id: str,
        properties: dict[str, Any],
        archived: bool | None = None,
    ) -> dict[str, Any]:
        """Update page properties. Pass archived=True to archive the page."""
        kwargs: dict[str, Any] = {"page_id": page_id, "properties": properties}
        if archived is not None:
            kwargs["archived"] = archived
        return self._client.pages.update(**kwargs)

    # ──────────────────────────────────────────────
    # Blocks
    # ──────────────────────────────────────────────

    def get_block(self, block_id: str) -> dict[str, Any]:
        return self._client.blocks.retrieve(block_id=block_id)

    def get_block_children(
        self, block_id: str, page_size: int = 100
    ) -> list[dict[str, Any]]:
        """Return all child blocks (handles pagination automatically)."""
        results: list[dict[str, Any]] = []
        cursor: str | None = None
        while True:
            kwargs: dict[str, Any] = {
                "block_id": block_id,
                "page_size": page_size,
            }
            if cursor:
                kwargs["start_cursor"] = cursor
            resp = self._client.blocks.children.list(**kwargs)
            results.extend(resp.get("results", []))
            if not resp.get("has_more"):
                break
            cursor = resp.get("next_cursor")
        return results

    def get_page_content(
        self, page_id: str, max_depth: int = 5
    ) -> list[dict[str, Any]]:
        """Full recursive page content — blocks and their nested children."""
        return self._fetch_blocks_recursive(page_id, max_depth=max_depth)

    def _fetch_blocks_recursive(
        self, block_id: str, depth: int = 0, max_depth: int = 5
    ) -> list[dict[str, Any]]:
        try:
            blocks = self.get_block_children(block_id)
        except APIResponseError as e:
            # Top-level block inaccessible (e.g. page not shared with integration)
            return [{"type": "_error", "id": block_id, "_access_error": str(e)}]
        if depth >= max_depth:
            return blocks

        indexed = [(i, b) for i, b in enumerate(blocks) if b.get("has_children")]
        if not indexed:
            return blocks

        par = max(1, min(int(os.environ.get("NOTION_FETCH_PARALLELISM", "6")), len(indexed)))

        def fetch_branch(idx: int, child_id: str) -> tuple[int, list[dict[str, Any]]]:
            # Separate Client per branch — httpx SyncClient is not shared across threads.
            c = Client(
                auth=self._api_key,
                client=httpx.Client(timeout=self._http_timeout),
            )
            try:
                return idx, _recursive_fill_subtree(c, child_id, depth + 1, max_depth)
            finally:
                c.close()

        if par == 1 or len(indexed) == 1:
            for idx, b in indexed:
                _, ch = fetch_branch(idx, b["id"])
                blocks[idx]["children"] = ch
        else:
            with ThreadPoolExecutor(max_workers=par) as pool:
                future_map = {
                    pool.submit(fetch_branch, idx, b["id"]): idx for idx, b in indexed
                }
                for fut in as_completed(future_map):
                    idx, ch = fut.result()
                    blocks[idx]["children"] = ch
        return blocks

    def append_blocks(
        self, block_id: str, children: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Append content blocks to a page or block."""
        return self._client.blocks.children.append(
            block_id=block_id, children=children
        )

    def update_block(
        self, block_id: str, block_type: str, content: dict[str, Any]
    ) -> dict[str, Any]:
        """
        Update a specific block.
        block_type: e.g. "paragraph", "heading_1", "to_do", etc.
        content: the inner content dict for that block type.
        """
        return self._client.blocks.update(
            block_id=block_id, **{block_type: content}
        )

    def delete_block(self, block_id: str) -> dict[str, Any]:
        return self._client.blocks.delete(block_id=block_id)

    # ──────────────────────────────────────────────
    # Databases
    # ──────────────────────────────────────────────

    def get_database(self, database_id: str) -> dict[str, Any]:
        """Fetch database schema (columns, types, options)."""
        return self._client.databases.retrieve(database_id=database_id)

    def query_database(
        self,
        database_id: str,
        filter: dict[str, Any] | None = None,
        sorts: list[dict[str, Any]] | None = None,
        page_size: int = 100,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        """
        Query a database. Handles pagination.
        limit: max total results (None = all).
        """
        # notion-client v3 removed databases.query — use httpx directly
        results: list[dict[str, Any]] = []
        cursor: str | None = None
        url = f"{_NOTION_API_BASE}/databases/{database_id}/query"
        while True:
            body: dict[str, Any] = {
                "page_size": min(page_size, limit - len(results)) if limit else page_size,
            }
            if filter:
                body["filter"] = filter
            if sorts:
                body["sorts"] = sorts
            if cursor:
                body["start_cursor"] = cursor
            read_t = float(os.environ.get("NOTION_HTTP_READ_TIMEOUT", "180"))
            resp = httpx.post(url, headers=self._headers, json=body, timeout=read_t)
            resp.raise_for_status()
            data = resp.json()
            results.extend(data.get("results", []))
            if limit and len(results) >= limit:
                break
            if not data.get("has_more"):
                break
            cursor = data.get("next_cursor")
        return results

    def create_database(
        self,
        parent_page_id: str,
        title: str,
        properties: dict[str, Any],
    ) -> dict[str, Any]:
        """Create a new database as a child of a page."""
        return self._client.databases.create(
            parent={"type": "page_id", "page_id": parent_page_id},
            title=[{"type": "text", "text": {"content": title}}],
            properties=properties,
        )

    def update_database(
        self,
        database_id: str,
        title: str | None = None,
        properties: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        kwargs: dict[str, Any] = {"database_id": database_id}
        if title:
            kwargs["title"] = [{"type": "text", "text": {"content": title}}]
        if properties:
            kwargs["properties"] = properties
        return self._client.databases.update(**kwargs)

    def create_database_entry(
        self,
        database_id: str,
        title: str,
        properties: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Add a row to a database."""
        return self.create_page(
            parent_id=database_id,
            title=title,
            properties=properties,
            is_database_entry=True,
        )

    # ──────────────────────────────────────────────
    # Search
    # ──────────────────────────────────────────────

    def search(
        self,
        query: str,
        filter_type: str | None = None,
        page_size: int = 20,
    ) -> list[dict[str, Any]]:
        """
        Full-text search across workspace.
        filter_type: "page" or "database" (None = both).
        """
        kwargs: dict[str, Any] = {"query": query, "page_size": page_size}
        if filter_type:
            kwargs["filter"] = {"value": filter_type, "property": "object"}
        resp = self._client.search(**kwargs)
        return resp.get("results", [])

    def get_by_title(
        self, title: str, filter_type: str | None = None
    ) -> list[dict[str, Any]]:
        """Find pages or databases by exact or partial title match."""
        results = self.search(title, filter_type=filter_type)
        # Filter to closest matches
        title_lower = title.lower()
        matched = [
            r
            for r in results
            if title_lower
            in self._extract_title(r).lower()
        ]
        return matched if matched else results

    @staticmethod
    def _extract_title(obj: dict[str, Any]) -> str:
        """Extract plain text title from a page or database object."""
        if obj.get("object") == "database":
            parts = obj.get("title", [])
        else:
            props = obj.get("properties", {})
            title_prop = next(
                (v for v in props.values() if v.get("type") == "title"), {}
            )
            parts = title_prop.get("title", [])
        return "".join(p.get("plain_text", "") for p in parts)

    # ──────────────────────────────────────────────
    # Comments
    # ──────────────────────────────────────────────

    def get_comments(self, page_id: str) -> list[dict[str, Any]]:
        resp = self._client.comments.list(block_id=page_id)
        return resp.get("results", [])

    def add_comment(self, page_id: str, text: str) -> dict[str, Any]:
        return self._client.comments.create(
            parent={"page_id": page_id},
            rich_text=[{"type": "text", "text": {"content": text}}],
        )

    # ──────────────────────────────────────────────
    # Users
    # ──────────────────────────────────────────────

    def get_users(self) -> list[dict[str, Any]]:
        resp = self._client.users.list()
        return resp.get("results", [])

    def get_me(self) -> dict[str, Any]:
        return self._client.users.me()
