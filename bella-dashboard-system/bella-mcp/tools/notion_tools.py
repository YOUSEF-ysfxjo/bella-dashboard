"""
Notion MCP tools — registered on the FastMCP server.
Full Notion API surface: pages, blocks, databases, search, comments, users.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from notion_tool_cache import (
    cached_read,
    invalidate_after_block_mutation,
    invalidate_after_page_mutation,
    invalidate_database,
    invalidate_page,
    invalidate_search,
)

if TYPE_CHECKING:
    from fastmcp import FastMCP
    from clients.notion import NotionClient


def register(mcp: "FastMCP", notion: "NotionClient") -> None:
    """Register all Notion tools on the MCP server."""

    # ──────────────────────────────────────────────
    # Pages
    # ──────────────────────────────────────────────

    @mcp.tool()
    def notion_get_page(page_id: str) -> dict[str, Any]:
        """
        Fetch a Notion page's metadata and properties.
        Returns the full page object including all property values.
        Use notion_get_page_content() to get the actual text/blocks inside.
        """
        return cached_read(
            "notion_get_page",
            {"page_id": page_id},
            lambda: notion.get_page(page_id),
            page_ids=(page_id,),
        )

    @mcp.tool()
    def notion_get_page_content(
        page_id: str,
        max_depth: int = 2,
    ) -> list[dict[str, Any]] | dict[str, Any]:
        """
        Get content blocks inside a Notion page. max_depth 1–5, default 2.
        Use for normal pages only. For databases use notion_query_database.

        IMPORTANT: If the response contains "_auto_outline: true", the page was too large
        for full content. Use notion_get_page_outline() to get block IDs, then
        notion_delete_block() / notion_append_blocks() to make changes.
        """
        depth = max(1, min(int(max_depth), 5))

        def fetch_and_guard() -> list[dict[str, Any]] | dict[str, Any]:
            blocks = notion.get_page_content(page_id, max_depth=depth)
            # Safety: if serialized result > 40 KB, return outline instead
            if len(json.dumps(blocks)) > 40_000:
                raw = notion.get_block_children(page_id)

                def _text(block: dict[str, Any]) -> str:
                    btype = block.get("type", "")
                    inner = block.get(btype, {})
                    if isinstance(inner, dict):
                        rt = inner.get("rich_text", inner.get("text", []))
                        if isinstance(rt, list):
                            return "".join(
                                s.get("plain_text", s.get("text", {}).get("content", ""))
                                for s in rt
                            )[:100]
                        return inner.get("title", "")
                    return ""

                return {
                    "_auto_outline": True,
                    "_message": (
                        "Page too large for full content. "
                        "Use notion_get_page_outline() to get block IDs for edits."
                    ),
                    "blocks": [
                        {
                            "id": b["id"],
                            "type": b.get("type", ""),
                            "text": _text(b),
                            "has_children": b.get("has_children", False),
                        }
                        for b in raw
                    ],
                }
            return blocks

        return cached_read(
            "notion_get_page_content",
            {"page_id": page_id, "max_depth": depth},
            fetch_and_guard,
            page_ids=(page_id,),
        )

    @mcp.tool()
    def notion_create_page(
        parent_id: str,
        title: str,
        is_database_entry: bool = False,
        properties: str = "{}",
        content_blocks: str = "[]",
    ) -> dict[str, Any]:
        """
        Create a new page. Set is_database_entry=True when parent_id is a database.
        properties: JSON string of Notion property values.
        content_blocks: JSON array of block objects to pre-populate.
        """
        props = json.loads(properties)
        blocks = json.loads(content_blocks)
        result = notion.create_page(
            parent_id=parent_id,
            title=title,
            properties=props if props else None,
            children=blocks if blocks else None,
            is_database_entry=is_database_entry,
        )
        if is_database_entry:
            invalidate_database(parent_id)
        else:
            invalidate_page(parent_id)
        invalidate_search()
        return result

    @mcp.tool()
    def notion_update_page(
        page_id: str,
        properties: str,
        archived: bool = False,
    ) -> dict[str, Any]:
        """
        Update a page's properties. properties: JSON string of property values.
        archived: Set True to archive (soft-delete) the page.
        """
        props = json.loads(properties)
        out = notion.update_page(page_id, props, archived=archived if archived else None)
        invalidate_after_page_mutation(page_id)
        return out

    @mcp.tool()
    def notion_append_blocks(
        block_id: str,
        children: str,
    ) -> dict[str, Any]:
        """
        Append content blocks to a page or block.
        block_id: Page ID or parent block ID to append to.
        children: JSON array string of block objects. Always use "rich_text" (NOT "text").

        to_do: [{"type":"to_do","to_do":{"rich_text":[{"type":"text","text":{"content":"Task"}}],"checked":false}}]
        paragraph: [{"type":"paragraph","paragraph":{"rich_text":[{"type":"text","text":{"content":"Hello"}}]}}]
        heading_3: [{"type":"heading_3","heading_3":{"rich_text":[{"type":"text","text":{"content":"Title"}}]}}]
        bulleted: [{"type":"bulleted_list_item","bulleted_list_item":{"rich_text":[{"type":"text","text":{"content":"Item"}}]}}]

        Split large appends into batches of ≤5 blocks each.
        """
        # Robustly extract the JSON array even if Bella appends extra characters
        raw = children.strip()
        # Find the last closing bracket of the array
        end = raw.rfind("]")
        if end == -1:
            raise ValueError("children must be a JSON array starting with [ and ending with ]")
        raw = raw[:end + 1]
        # Find the first opening bracket
        start = raw.find("[")
        if start == -1:
            raise ValueError("children must be a JSON array starting with [")
        raw = raw[start:]
        blocks: list[dict[str, Any]] = json.loads(raw)
        # Normalize old-style 'text' → 'rich_text'
        BLOCK_TYPES = {"paragraph", "heading_1", "heading_2", "heading_3", "to_do",
                       "bulleted_list_item", "numbered_list_item", "quote", "callout"}
        for block in blocks:
            btype = block.get("type", "")
            if btype in BLOCK_TYPES and btype in block:
                inner = block[btype]
                if "text" in inner and "rich_text" not in inner:
                    inner["rich_text"] = inner.pop("text")
        out = notion.append_blocks(block_id, blocks)
        invalidate_after_block_mutation(block_id)
        return out

    @mcp.tool()
    def notion_get_page_outline(page_id: str) -> list[dict[str, Any]]:
        """
        Get a compact, flat outline of a page's direct child blocks.
        Returns [{id, type, text, has_children}] — NO recursion into child pages.

        Use this INSTEAD of notion_get_page_content when you need to:
        - Find specific block IDs (e.g. to delete duplicate blocks)
        - Understand page structure without full content
        - Avoid context window overflow on large pages

        After getting block IDs, use notion_delete_block() or notion_append_blocks() to modify.
        """

        def _extract_text(block: dict[str, Any]) -> str:
            btype = block.get("type", "")
            inner = block.get(btype, {})
            if isinstance(inner, dict):
                rich = inner.get("rich_text", inner.get("text", []))
                if isinstance(rich, list):
                    return "".join(
                        seg.get("plain_text", seg.get("text", {}).get("content", ""))
                        for seg in rich
                    )[:120]
                # child_page / child_database
                return inner.get("title", "")
            return ""

        def fetch() -> list[dict[str, Any]]:
            blocks = notion.get_block_children(page_id)
            return [
                {
                    "id": b["id"],
                    "type": b.get("type", ""),
                    "text": _extract_text(b),
                    "has_children": b.get("has_children", False),
                }
                for b in blocks
            ]

        return cached_read(
            "notion_get_page_outline",
            {"page_id": page_id},
            fetch,
            page_ids=(page_id,),
        )

    @mcp.tool()
    def notion_get_block_children(block_id: str) -> list[dict[str, Any]]:
        """Get the direct child blocks of a page or block."""
        return cached_read(
            "notion_get_block_children",
            {"block_id": block_id},
            lambda: notion.get_block_children(block_id),
            page_ids=(block_id,),
        )

    @mcp.tool()
    def notion_get_subpages(page_id: str) -> list[dict[str, Any]]:
        """
        Get all child pages and child databases embedded inside a page.
        Use this when you want to find sub-pages of a given page (e.g. April → Week 1, Week 2, etc.).
        Returns a list of {id, title, type} dicts for each child_page or child_database block found.
        Always use this after notion_get_by_title() when looking for sub-pages.
        """

        def fetch() -> list[dict[str, Any]]:
            blocks = notion.get_block_children(page_id)
            subpages = []
            for block in blocks:
                btype = block.get("type", "")
                if btype == "child_page":
                    title = block.get("child_page", {}).get("title", "")
                    subpages.append({"id": block["id"], "title": title, "type": "page"})
                elif btype == "child_database":
                    title = block.get("child_database", {}).get("title", "")
                    subpages.append({"id": block["id"], "title": title, "type": "database"})
            return subpages

        return cached_read(
            "notion_get_subpages",
            {"page_id": page_id},
            fetch,
            page_ids=(page_id,),
        )

    @mcp.tool()
    def notion_update_block(
        block_id: str,
        block_type: str,
        content: str,
    ) -> dict[str, Any]:
        """
        Update a specific block's content.
        block_type: e.g. "paragraph", "heading_1", "to_do". content: JSON string of inner content.
        """
        content_dict = json.loads(content)
        out = notion.update_block(block_id, block_type, content_dict)
        invalidate_after_block_mutation(block_id)
        return out

    @mcp.tool()
    def notion_delete_block(block_id: str) -> dict[str, Any]:
        """Delete (archive) a specific block from a page."""
        out = notion.delete_block(block_id)
        invalidate_after_block_mutation(block_id)
        return out

    # ──────────────────────────────────────────────
    # Databases
    # ──────────────────────────────────────────────

    @mcp.tool()
    def notion_get_database(database_id: str) -> dict[str, Any]:
        """
        Get a database's schema: all column names, types, and options.
        Use this to understand what properties a database has before querying or creating entries.
        """
        return cached_read(
            "notion_get_database",
            {"database_id": database_id},
            lambda: notion.get_database(database_id),
            database_ids=(database_id,),
        )

    @mcp.tool()
    def notion_query_database(
        database_id: str,
        filter: str = "{}",
        sorts: str = "[]",
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """
        Query a database with optional filters and sorting.
        filter: JSON string Notion filter. sorts: JSON array of sort objects. limit: max results.
        """
        filter_obj = json.loads(filter) if filter and filter != "{}" else None
        sorts_list = json.loads(sorts) if sorts and sorts != "[]" else None
        return cached_read(
            "notion_query_database",
            {
                "database_id": database_id,
                "filter": filter_obj,
                "sorts": sorts_list,
                "limit": limit,
            },
            lambda: notion.query_database(
                database_id=database_id,
                filter=filter_obj,
                sorts=sorts_list,
                limit=limit,
            ),
            database_ids=(database_id,),
        )

    @mcp.tool()
    def notion_create_database(
        parent_page_id: str,
        title: str,
        properties: str,
    ) -> dict[str, Any]:
        """
        Create a new database as a child of a page.
        properties: JSON string defining columns (Notion property schema).
        """
        props = json.loads(properties)
        out = notion.create_database(parent_page_id, title, props)
        invalidate_page(parent_page_id)
        invalidate_search()
        return out

    @mcp.tool()
    def notion_update_database(
        database_id: str,
        title: str = "",
        properties: str = "{}",
    ) -> dict[str, Any]:
        """
        Rename a database or modify its columns.
        title: New title (leave empty to keep current).
        properties: JSON string of property updates.
        """
        props = json.loads(properties)
        out = notion.update_database(
            database_id,
            title=title if title else None,
            properties=props if props else None,
        )
        invalidate_database(database_id)
        return out

    @mcp.tool()
    def notion_create_database_entry(
        database_id: str,
        title: str,
        properties: str = "{}",
    ) -> dict[str, Any]:
        """
        Add a new row to a database.
        title: Value for the title column. properties: JSON string of other column values.
        """
        props = json.loads(properties)
        out = notion.create_database_entry(database_id, title, props if props else None)
        invalidate_database(database_id)
        return out

    # ──────────────────────────────────────────────
    # Search & Discovery
    # ──────────────────────────────────────────────

    @mcp.tool()
    def notion_search(
        query: str,
        filter_type: str = "",
    ) -> list[dict[str, Any]]:
        """
        Full-text search across the entire Notion workspace.
        query: Search text.
        filter_type: "page", "database", or "" for both.
        Returns matching pages and databases with their IDs and titles.
        """
        return cached_read(
            "notion_search",
            {"query": query, "filter_type": filter_type or ""},
            lambda: notion.search(query, filter_type=filter_type if filter_type else None),
            search=True,
        )

    @mcp.tool()
    def notion_get_by_title(
        title: str,
        filter_type: str = "",
    ) -> list[dict[str, Any]]:
        """
        Find a page or database by its title (partial match supported).
        Use this when you know the name but not the ID.
        Example: notion_get_by_title("Trainee Work") → returns the page with that name.
        """
        return cached_read(
            "notion_get_by_title",
            {"title": title, "filter_type": filter_type or ""},
            lambda: notion.get_by_title(title, filter_type=filter_type if filter_type else None),
            search=True,
        )

    # ──────────────────────────────────────────────
    # Comments
    # ──────────────────────────────────────────────

    @mcp.tool()
    def notion_get_comments(page_id: str) -> list[dict[str, Any]]:
        """Get all comments and discussions on a Notion page."""
        return cached_read(
            "notion_get_comments",
            {"page_id": page_id},
            lambda: notion.get_comments(page_id),
            page_ids=(page_id,),
        )

    @mcp.tool()
    def notion_add_comment(page_id: str, text: str) -> dict[str, Any]:
        """Add a comment to a Notion page."""
        out = notion.add_comment(page_id, text)
        invalidate_page(page_id)
        return out

    # ──────────────────────────────────────────────
    # Users & Teams
    # ──────────────────────────────────────────────

    @mcp.tool()
    def notion_get_users() -> list[dict[str, Any]]:
        """List all members in the Notion workspace."""
        return cached_read(
            "notion_get_users",
            {},
            lambda: notion.get_users(),
        )

    @mcp.tool()
    def notion_get_me() -> dict[str, Any]:
        """Get info about the Bella integration bot user."""
        return cached_read(
            "notion_get_me",
            {},
            lambda: notion.get_me(),
        )

