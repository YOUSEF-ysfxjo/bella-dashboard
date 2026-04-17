#!/usr/bin/env python3
"""
Dry-run Bella MCP lifespan and list tools + resources (no HTTP, no API calls to Notion/GitHub).
Uses .env from bella-mcp if present. Exit 1 if lifespan fails or zero tools from always-on groups.
"""

from __future__ import annotations

import asyncio
import os
import sys

# bella-mcp root (parent of scripts/)
_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
os.chdir(_ROOT)

# Avoid hanging on Google OAuth/token refresh when credentials.json exists in bella-mcp/.
os.environ.setdefault("BELLA_DISABLE_CALENDAR", "1")


async def main() -> int:
    from server import lifespan, mcp

    try:
        async with lifespan(mcp):
            tools = await mcp.list_tools(run_middleware=False)
            names = sorted(t.name for t in tools)
            print(f"Listed tools: {len(names)}")
            for n in names:
                print(f"  - {n}")

            resources = await mcp.list_resources(run_middleware=False)
            ruris = sorted(getattr(r, "uri", str(r)) for r in resources)
            print(f"\nResources: {len(ruris)}")
            for u in ruris:
                print(f"  - {u}")

            # These register without cloud credentials
            always = {"fs_read", "fs_list", "shell_run", "web_search", "web_fetch"}
            missing = sorted(always - set(names))
            if missing:
                print(f"\nERROR: Expected universal tools missing: {missing}", file=sys.stderr)
                return 1

    except Exception as e:
        print(f"Lifespan or list failed: {e}", file=sys.stderr)
        return 1

    print("\nOK — lifespan completed and core filesystem/shell/web tools are present.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
