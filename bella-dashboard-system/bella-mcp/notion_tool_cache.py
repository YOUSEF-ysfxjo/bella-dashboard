"""
In-memory cache for read-only Notion MCP tools.

NOTION_TOOL_CACHE_TTL_SECONDS:
  - Positive number: seconds until entry expires (default 3600).
  - 0, off, false: disable caching.
  - -1, never, infinite: entries never expire (still invalidated on writes).
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import time
from typing import Any, Callable, TypeVar

T = TypeVar("T")


def _parse_ttl_seconds() -> float | None:
    raw = os.environ.get("NOTION_TOOL_CACHE_TTL_SECONDS", "3600").strip().lower()
    if raw in ("0", "off", "false", "no", "disabled"):
        return 0.0
    if raw in ("-1", "never", "inf", "infinite", "forever"):
        return None
    try:
        v = float(raw)
        if v < 0:
            return None
        return v
    except ValueError:
        return 3600.0


_config_done: bool = False
_ttl_seconds: float | None = 3600.0

# key -> {"value", "expires_at" (monotonic; None = never), "dbs", "pages", "search"}
_entries: dict[str, dict[str, Any]] = {}
_db_to_keys: dict[str, set[str]] = {}
_page_to_keys: dict[str, set[str]] = {}
_search_keys: set[str] = set()


def _ensure_config() -> None:
    global _config_done, _ttl_seconds
    if _config_done:
        return
    _ttl_seconds = _parse_ttl_seconds()
    _config_done = True


def is_enabled() -> bool:
    _ensure_config()
    return _ttl_seconds != 0.0


def describe_ttl() -> str:
    """Human-readable cache mode for logs."""
    _ensure_config()
    if _ttl_seconds == 0.0:
        return "disabled"
    if _ttl_seconds is None:
        return "no expiry (invalidates on write)"
    return f"{int(_ttl_seconds)}s TTL"


def _norm_id(raw: str) -> str:
    return raw.replace("-", "").strip()


def cache_key(tool: str, args: dict[str, Any]) -> str:
    canonical = json.dumps(args, sort_keys=True, separators=(",", ":"), default=str)
    digest = hashlib.sha256(canonical.encode()).hexdigest()[:24]
    return f"{tool}:{digest}"


def _now() -> float:
    return time.monotonic()


def _purge_key(key: str) -> None:
    meta = _entries.pop(key, None)
    if not meta:
        return
    for db in meta.get("dbs", ()):
        nid = _norm_id(db)
        s = _db_to_keys.get(nid)
        if s:
            s.discard(key)
            if not s:
                del _db_to_keys[nid]
    for page in meta.get("pages", ()):
        pid = _norm_id(page)
        s = _page_to_keys.get(pid)
        if s:
            s.discard(key)
            if not s:
                del _page_to_keys[pid]
    if meta.get("search"):
        _search_keys.discard(key)


def _expire_due() -> None:
    _ensure_config()
    if _ttl_seconds is None:
        return
    t = _now()
    dead = [k for k, m in _entries.items() if m["expires_at"] is not None and m["expires_at"] <= t]
    for k in dead:
        _purge_key(k)


def get_cached(key: str) -> Any | None:
    _ensure_config()
    if _ttl_seconds == 0.0:
        return None
    _expire_due()
    meta = _entries.get(key)
    if not meta:
        return None
    exp = meta["expires_at"]
    if exp is not None and exp <= _now():
        _purge_key(key)
        return None
    return copy.deepcopy(meta["value"])


def set_cached(
    key: str,
    value: Any,
    *,
    database_ids: tuple[str, ...] = (),
    page_ids: tuple[str, ...] = (),
    search: bool = False,
) -> None:
    _ensure_config()
    if _ttl_seconds == 0.0:
        return
    _expire_due()
    if key in _entries:
        _purge_key(key)
    exp: float | None
    if _ttl_seconds is None:
        exp = None
    else:
        exp = _now() + _ttl_seconds
    meta = {
        "value": copy.deepcopy(value),
        "expires_at": exp,
        "dbs": database_ids,
        "pages": page_ids,
        "search": search,
    }
    _entries[key] = meta
    for db in database_ids:
        nid = _norm_id(db)
        if nid:
            _db_to_keys.setdefault(nid, set()).add(key)
    for page in page_ids:
        pid = _norm_id(page)
        if pid:
            _page_to_keys.setdefault(pid, set()).add(key)
    if search:
        _search_keys.add(key)


def cached_read(
    tool: str,
    args: dict[str, Any],
    fetch: Callable[[], T],
    *,
    database_ids: tuple[str, ...] = (),
    page_ids: tuple[str, ...] = (),
    search: bool = False,
) -> T:
    _ensure_config()
    if _ttl_seconds == 0.0:
        return fetch()
    key = cache_key(tool, args)
    hit = get_cached(key)
    if hit is not None:
        return hit
    fresh = fetch()
    set_cached(key, fresh, database_ids=database_ids, page_ids=page_ids, search=search)
    return copy.deepcopy(fresh)


def invalidate_database(database_id: str) -> None:
    nid = _norm_id(database_id)
    if not nid:
        return
    for k in list(_db_to_keys.get(nid, ())):
        _purge_key(k)


def invalidate_page(page_id: str) -> None:
    pid = _norm_id(page_id)
    if not pid:
        return
    for k in list(_page_to_keys.get(pid, ())):
        _purge_key(k)


def invalidate_search() -> None:
    for k in list(_search_keys):
        _purge_key(k)


def configured_notion_database_ids() -> frozenset[str]:
    ids: set[str] = set()
    env_keys = (
        "NOTION_TASKS_DB_ID",
        "NOTION_TASKS_DB",
        "NOTION_PROJECTS_DB_ID",
        "NOTION_PROJECTS_DB",
        "NOTION_PAPER_READING_DB",
        "NOTION_BELLA_MEMORY_DB",
    )
    for name in env_keys:
        v = os.environ.get(name, "").strip().replace("-", "")
        if len(v) >= 32:
            ids.add(v)
    return frozenset(ids)


def invalidate_all_known_database_queries() -> None:
    for db in configured_notion_database_ids():
        invalidate_database(db)


def invalidate_after_page_mutation(page_id: str) -> None:
    invalidate_page(page_id)
    invalidate_all_known_database_queries()


def invalidate_after_block_mutation(block_id: str) -> None:
    invalidate_page(block_id)
    invalidate_all_known_database_queries()
