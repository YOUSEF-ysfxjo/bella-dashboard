"""
MCP Resources — auto-loaded context provided to Bella at the start of every session.
These are equivalent to Moasherat's entities_cache: pre-fetched at startup, always available.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from fastmcp import FastMCP
    from clients.notion import NotionClient


# ──────────────────────────────────────────────────────────────
# In-memory caches (populated at startup via lifespan in server.py)
# ──────────────────────────────────────────────────────────────

_notion_db_schemas: dict[str, Any] = {}
_yousef_profile: str = ""


def populate_caches(notion: "NotionClient") -> None:
    """
    Called once at server startup.
    Pre-fetches Notion database schemas.
    """
    global _notion_db_schemas, _yousef_profile

    # ── Notion database schemas ──────────────────────────────
    db_env_vars = {
        "tasks": os.environ.get("NOTION_TASKS_DB_ID", ""),
        "projects": os.environ.get("NOTION_PROJECTS_DB_ID", ""),
        "research": os.environ.get("NOTION_RESEARCH_PAGE_ID", ""),
    }

    for name, db_id in db_env_vars.items():
        if not db_id:
            continue
        try:
            if name == "research":
                # It's a page, not a database — fetch metadata
                page = notion.get_page(db_id)
                _notion_db_schemas[name] = {
                    "id": db_id,
                    "type": "page",
                    "title": _extract_page_title(page),
                }
            else:
                db = notion.get_database(db_id)
                _notion_db_schemas[name] = {
                    "id": db_id,
                    "type": "database",
                    "title": _extract_db_title(db),
                    "properties": {
                        k: v.get("type") for k, v in db.get("properties", {}).items()
                    },
                }
            print(f"[Bella] Loaded Notion schema: {name} ✓")
        except Exception as e:
            print(f"[Bella] Warning: Could not load '{name}' schema: {e}")

    # ── Yousef profile (static, from env or hardcoded defaults) ──
    _yousef_profile = _build_profile()
    print("[Bella] Profile loaded ✓")


def register(mcp: "FastMCP") -> None:
    """Register context resources on the MCP server."""

    @mcp.resource("context://yousef_profile")
    def yousef_profile() -> str:
        """
        Yousef Ammar's current context: roles, projects, Q2 2026 priorities.
        Auto-loaded at session start.
        """
        return _yousef_profile

    @mcp.resource("context://notion_databases")
    def notion_databases() -> str:
        """
        Notion database/page IDs and schemas for fast reference.
        Auto-loaded at session start — no need to call notion_get_database() for known DBs.
        """
        if not _notion_db_schemas:
            return "No Notion databases configured. Set NOTION_TASKS_DB_ID etc. in .env"
        lines = ["Available Notion data sources:\n"]
        for name, schema in _notion_db_schemas.items():
            lines.append(f"  [{name}]")
            lines.append(f"    ID: {schema['id']}")
            lines.append(f"    Type: {schema['type']}")
            lines.append(f"    Title: {schema.get('title', 'N/A')}")
            if schema.get("properties"):
                props = ", ".join(
                    f"{k} ({v})" for k, v in schema["properties"].items()
                )
                lines.append(f"    Columns: {props}")
            lines.append("")
        return "\n".join(lines)

# ──────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────

def _extract_db_title(db: dict[str, Any]) -> str:
    parts = db.get("title", [])
    return "".join(p.get("plain_text", "") for p in parts)


def _extract_page_title(page: dict[str, Any]) -> str:
    props = page.get("properties", {})
    title_prop = next(
        (v for v in props.values() if v.get("type") == "title"), {}
    )
    parts = title_prop.get("title", [])
    return "".join(p.get("plain_text", "") for p in parts)


def _build_profile() -> str:
    return """
Yousef Ammar — Personal Context for Bella
==========================================
Role: Data Scientist @ Qanoniah + AI Engineer @ Moasherat (both active)
University: Umm Al-Qura University, Data Science 3rd year (graduating 2027)
Location: Makkah, Saudi Arabia
Age: 21

Current Q2 2026 Priorities:
1. Finish research paper (XAI + Federated Learning on Arabic complaints)
   - ~80% done. Remaining: fix Figure 5, expand LIME analysis, add inter-annotator agreement,
     remove/address FedProx, choose venue (IEEE Access target), add ethics statement
2. Make HuggingFace models public (text-complaint-api uses them)
3. Fill HF model cards
4. KAUST MSc application — research paper is the missing piece

Active Projects:
- text-complaint-api: FastAPI + MARBERT, deployed Railway
- github_cleaner: Portfolio analyzer API, deployed Render
- ml-nlp-guide: NLP learning project (Phase B: contextual embeddings in progress)
- Bella System: This agent (long-term flagship project)
- daily-brief: Daily arXiv + RSS briefing tool
- research_harvester: arXiv → MinIO → Qdrant pipeline

HuggingFace Models (currently private — need to make public):
- Ysfxjo/marbert-complaint-sentiment (76.0% acc)
- Ysfxjo/marbert-saudi-complaint-topic (99.1% acc)
- Ysfxjo/marbert-saudi-complaint-action (99.6% acc)

GitHub: YOUSEF-ysfxjo
HuggingFace: Ysfxjo
Notion workspace: https://www.notion.so/2026-2db92e6818f881a0b17dd5cf1e791d05

AI Usage Principle: LLM explains. It does NOT decide.
Deterministic boundaries preserved in all production systems.
""".strip()
