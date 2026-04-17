# bella-mcp

Personal AI Agent MCP server for Yousef Ammar.
Connects to Notion, GitHub, and Google Calendar via the Model Context Protocol.

---

## Architecture

```
Dashboard client (or any MCP-compatible client)
    ↓ streamable-http MCP
bella-mcp (Port 3001)
    ├── Notion API  → pages, databases, search
    ├── GitHub API  → repos, commits, issues, files
    └── Google Calendar API → events, free time, scheduling
```

---

## Quick Start

### 1. Set up environment

```bash
cp .env.example .env
# Edit .env with your API keys
```

### 2. Set up Google Calendar (one-time)

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a project → Enable **Google Calendar API**
3. Create OAuth2 credentials (Desktop app type)
4. Download `credentials.json` → place it in this folder (`bella-mcp/`)
5. On first run, a browser window opens for OAuth consent → approves and saves `token.json`

### 3. Set up Notion

1. Go to [notion.so/my-integrations](https://www.notion.so/my-integrations) → Create integration
2. Copy the API key → paste into `.env` as `NOTION_API_KEY`
3. In each Notion page/database you want Bella to access:
   - Open the page → `...` menu → **Connections** → Add your integration
4. (Optional) Create/update wiki notes for persistent context if you want long-term continuity.

### 4. Run locally

```bash
# Install uv if you don't have it
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install dependencies
uv sync

# Run MCP server
uv run python server.py
```

Server starts at `http://localhost:3001/mcp`

### 4.1 Run dashboard chat API (for in-page Bella chat)

```bash
uv run python chat_api.py
```

Chat API starts at `http://localhost:3002/chat`

For a deployed frontend (e.g. Netlify), deploy this API on a public URL, then set it in the dashboard once:

```js
localStorage.setItem("bella-chat-api-url", "https://your-chat-api-domain/chat");
```

Or open the page with:

```text
?chatApi=https://your-chat-api-domain/chat
```

### 5. Run with Docker

From this `bella-mcp/` folder:

```bash
docker build -t bella-dashboard-mcp .
docker run --rm -p 3001:3001 --env-file .env bella-dashboard-mcp
```

- Bella MCP: `http://localhost:3001/mcp`

---

## Project Structure

```
bella-mcp/
├── server.py              # Entry point — FastMCP server + lifespan
├── resources.py           # Context resources (auto-loaded at session start)
├── system_prompt.txt      # Bella's personality + behavior rules
│
├── clients/
│   ├── notion.py          # Full Notion API client
│   ├── github.py          # GitHub API client (PyGithub)
│   └── calendar.py        # Google Calendar API client
│
├── tools/
│   ├── notion_tools.py    # Notion MCP tools
│   ├── github_tools.py    # ~9 GitHub MCP tools
│   └── calendar_tools.py  # ~7 Calendar MCP tools
│
├── pyproject.toml         # Dependencies (fastmcp, notion-client, PyGithub, google-api)
├── Dockerfile
├── .env.example
└── .python-version        # 3.12
```

---

## Extending Bella

### Add a new tool

In any file in `tools/`, add a new `@mcp.tool()` function inside the `register()` function:

```python
@mcp.tool()
def my_new_tool(arg1: str, arg2: int = 10) -> dict:
    """
    Description of what this tool does.
    Bella uses this docstring to decide when to call it.
    """
    result = my_client.do_something(arg1, arg2)
    return result
```

The function signature becomes the tool schema automatically (FastMCP handles it).

### Add a new data source

1. Create `clients/mysource.py` with a client class
2. Create `tools/mysource_tools.py` with a `register(mcp, client)` function
3. In `server.py`, initialize the client and call `register_mysource(server, client)` in lifespan
4. Add any API keys to `.env.example`

### Change Bella's behavior

Edit `system_prompt.txt` — Bella's personality, priorities, and rules are all there.

### Add a new Notion database

1. In Notion: share the database with the integration
2. Add its ID to `.env`: `NOTION_MY_DB_ID=...`
3. In `resources.py`, add it to the `db_env_vars` dict in `populate_caches()`

---

## Available Tools

### Notion (~20 tools)

**Pages:** `notion_get_page`, `notion_get_page_content`, `notion_create_page`, `notion_update_page`, `notion_append_blocks`, `notion_get_block_children`, `notion_update_block`, `notion_delete_block`

**Databases:** `notion_get_database`, `notion_query_database`, `notion_create_database`, `notion_update_database`, `notion_create_database_entry`

**Search:** `notion_search`, `notion_get_by_title`

**Comments:** `notion_get_comments`, `notion_add_comment`

**Users:** `notion_get_users`, `notion_get_me`

**Memory:** handled through wiki tooling (no memory-specific MCP tools in this dashboard build)

### GitHub (9 tools)

`github_list_repos`, `github_get_repo`, `github_get_readme`, `github_list_issues`, `github_get_issue`, `github_create_issue`, `github_list_commits`, `github_get_file`, `github_search_code`, `github_list_prs`

### Google Calendar (7 tools)

`calendar_list_calendars`, `calendar_list_events`, `calendar_get_today`, `calendar_get_week`, `calendar_create_event`, `calendar_update_event`, `calendar_delete_event`, `calendar_find_free_time`

### Context Resources (auto-loaded)

`context://yousef_profile` — Current projects, roles, priorities
`context://notion_databases` — Database IDs and schemas
`context://notion_databases` + wiki notes are used for persistent context

---

## Future Phases

- **Phase 2:** Telegram bot interface (same MCP server, new transport)
- **Phase 3:** n8n automation → push data to Notion → Bella reads it
- **Phase 4:** Mobile/web app with Whisper voice input
