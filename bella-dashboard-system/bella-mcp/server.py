"""
Bella MCP Server — Personal AI Agent for Yousef Ammar.

Architecture:
  Dashboard/Client → [streamable-http MCP] → bella-mcp → Notion + GitHub + Google Calendar

Run locally:
  uv run python server.py

Run with Docker:
  docker compose up
"""

from __future__ import annotations

import os
import sys
from contextlib import asynccontextmanager
from typing import AsyncIterator

from dotenv import load_dotenv
from fastmcp import FastMCP

# ──────────────────────────────────────────────────────────────
# Load environment
# ──────────────────────────────────────────────────────────────
load_dotenv()

# ──────────────────────────────────────────────────────────────
# System prompt
# ──────────────────────────────────────────────────────────────

def _load_system_prompt() -> str:
    prompt_path = os.path.join(os.path.dirname(__file__), "system_prompt.txt")
    try:
        with open(prompt_path, encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return "You are Bella, Yousef Ammar's personal AI assistant."


# ──────────────────────────────────────────────────────────────
# Client initialization (lazy — skipped if env vars missing)
# ──────────────────────────────────────────────────────────────

def _init_notion():
    from clients.notion import NotionClient
    return NotionClient()


def _init_github():
    from clients.github import GitHubClient
    return GitHubClient()


def _init_calendar():
    from clients.calendar import CalendarClient
    return CalendarClient()


def _init_obsidian():
    from clients.obsidian import ObsidianClient
    return ObsidianClient()


def _init_shell():
    from clients.shell import ShellClient
    return ShellClient()


def _init_filesystem():
    from clients.filesystem import FilesystemClient
    return FilesystemClient()


def _init_web():
    from clients.web import WebClient
    return WebClient()


# ──────────────────────────────────────────────────────────────
# Server lifespan — startup cache (like Moasherat's entities_cache)
# ──────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(server: FastMCP) -> AsyncIterator[None]:
    print("[Bella] Starting up...")

    # Initialize clients
    notion = None
    github = None
    calendar = None

    if os.environ.get("NOTION_API_KEY"):
        try:
            notion = _init_notion()
            print("[Bella] Notion client initialized ✓")
        except Exception as e:
            print(f"[Bella] Warning: Notion unavailable: {e}")
    else:
        print("[Bella] Warning: NOTION_API_KEY not set — Notion tools disabled")

    if os.environ.get("GITHUB_TOKEN"):
        try:
            github = _init_github()
            print("[Bella] GitHub client initialized ✓")
        except Exception as e:
            print(f"[Bella] Warning: GitHub unavailable: {e}")
    else:
        print("[Bella] Warning: GITHUB_TOKEN not set — GitHub tools disabled")

    calendar_disabled = os.environ.get("BELLA_DISABLE_CALENDAR", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )
    if calendar_disabled:
        print("[Bella] Calendar disabled via BELLA_DISABLE_CALENDAR — Calendar tools skipped")
    elif os.environ.get("GOOGLE_CREDENTIALS_JSON") or os.path.exists("credentials.json"):
        try:
            calendar = _init_calendar()
            print("[Bella] Calendar client initialized ✓")
        except Exception as e:
            print(f"[Bella] Warning: Calendar unavailable: {e}")
    else:
        print("[Bella] Warning: GOOGLE_CREDENTIALS_JSON not set — Calendar tools disabled")

    obsidian = None
    if os.environ.get("OBSIDIAN_VAULT_PATH"):
        try:
            obsidian = _init_obsidian()
            print("[Bella] Obsidian client initialized ✓")
        except Exception as e:
            print(f"[Bella] Warning: Obsidian unavailable: {e}")
    else:
        print("[Bella] Warning: OBSIDIAN_VAULT_PATH not set — Obsidian tools disabled")

    # Pre-fetch Notion schemas
    if notion:
        try:
            from resources import populate_caches
            populate_caches(notion)
        except Exception as e:
            print(f"[Bella] Warning: Cache population failed: {e}")

    # Register tools (only for available clients)
    if notion:
        from tools.notion_tools import register as register_notion
        from notion_tool_cache import describe_ttl

        register_notion(server, notion)
        print(f"[Bella] Notion tools registered ✓ (read cache: {describe_ttl()})")

    if github:
        from tools.github_tools import register as register_github
        register_github(server, github)
        print("[Bella] GitHub tools registered ✓")

    if calendar:
        from tools.calendar_tools import register as register_calendar
        register_calendar(server, calendar)
        print("[Bella] Calendar tools registered ✓")

    if obsidian:
        from tools.obsidian_tools import register as register_obsidian
        register_obsidian(server, obsidian)
        print("[Bella] Obsidian tools registered ✓")

        from tools.wiki_tools import register as register_wiki
        register_wiki(server, obsidian)
        print("[Bella] Wiki tools registered ✓")

    # Shell — always available (no credentials needed)
    try:
        shell = _init_shell()
        from tools.shell_tools import register as register_shell
        register_shell(server, shell)
        print("[Bella] Shell tools registered ✓")
    except Exception as e:
        print(f"[Bella] Warning: Shell unavailable: {e}")

    # File system — always available
    try:
        fs = _init_filesystem()
        from tools.filesystem_tools import register as register_fs
        register_fs(server, fs)
        print("[Bella] Filesystem tools registered ✓")
    except Exception as e:
        print(f"[Bella] Warning: Filesystem unavailable: {e}")

    # Web — always available
    try:
        web = _init_web()
        from tools.web_tools import register as register_web
        register_web(server, web)
        print("[Bella] Web tools registered ✓")
    except Exception as e:
        print(f"[Bella] Warning: Web unavailable: {e}")

    print("[Bella] Ready. Listening for connections...")
    yield

    print("[Bella] Shutting down.")


# ──────────────────────────────────────────────────────────────
# MCP Server
# ──────────────────────────────────────────────────────────────

mcp = FastMCP(
    name="bella",
    instructions=_load_system_prompt(),
    lifespan=lifespan,
)

# Register context resources (always available, even without live clients)
from resources import register as register_resources
register_resources(mcp)


# ──────────────────────────────────────────────────────────────
# Entry point
# ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    host = os.environ.get("MCP_HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "3001"))

    print(f"[Bella] Starting MCP server on http://{host}:{port}/mcp")
    mcp.run(
        transport="streamable-http",
        host=host,
        port=port,
        path="/mcp",
    )
