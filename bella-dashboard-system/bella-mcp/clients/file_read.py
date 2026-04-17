"""
Resilient UTF-8 reads for Docker bind mounts from macOS/Colima (errno 35 deadlocks).
"""

from __future__ import annotations

import os
import subprocess
import time


def read_utf8_resilient(path: str) -> str:
    """
    Read a file as UTF-8 with retries and a cat(1) fallback.
    Returns "" only if the file is missing, empty, or all strategies failed.
    """
    if not path or not os.path.isfile(path):
        return ""

    backoff = 0.06
    for attempt in range(22):
        try:
            with open(path, "rb") as f:
                data = f.read()
            return data.decode("utf-8", errors="ignore")
        except OSError as e:
            if e.errno != 35 or attempt >= 21:
                break
            time.sleep(min(1.2, backoff))
            backoff *= 1.35

    for attempt in range(6):
        try:
            proc = subprocess.run(
                ["/bin/cat", path],
                capture_output=True,
                timeout=45,
                check=False,
            )
            if proc.returncode == 0 and proc.stdout:
                return proc.stdout.decode("utf-8", errors="ignore")
        except (OSError, subprocess.TimeoutExpired):
            pass
        time.sleep(0.15 * (attempt + 1))

    # 3) dd — different kernel path than Python/cat; helps some Colima bind mounts (errno 35).
    for attempt in range(4):
        try:
            proc = subprocess.run(
                ["/bin/dd", f"if={path}", "bs=262144", "status=none"],
                capture_output=True,
                timeout=60,
                check=False,
            )
            if proc.returncode == 0 and proc.stdout:
                return proc.stdout.decode("utf-8", errors="ignore")
        except (OSError, subprocess.TimeoutExpired):
            pass
        time.sleep(0.2 * (attempt + 1))

    return ""


def read_utf8_or_error_message(path: str) -> str:
    """Return file text, or a clear error string if the file exists but could not be read."""
    if not os.path.isfile(path):
        return f"[READ ERROR: file not found: {path}]"
    body = read_utf8_resilient(path)
    if body:
        return body
    try:
        sz = os.path.getsize(path)
    except OSError as e:
        return f"[READ ERROR: could not stat after retries: {e}]"
    if sz == 0:
        return ""
    return (
        "[READ ERROR: bind-mount I/O failed after retries (macOS/Colima errno 35). "
        "Fix A: colima stop && colima start --mount-type virtiofs — then docker compose up -d. "
        "Fix B: close Obsidian (or INDEX.md tab), rebuild bella-mcp. "
        "Fix C: run MCP on the Mac (no vault bind mount): "
        "docker compose stop bella-mcp && cd bella-mcp && OBSIDIAN_VAULT_PATH=\"$HOME/Documents/Obsidian Vault\" uv run python server.py "
        "— and point LibreChat MCP URL to http://host.docker.internal:3001/mcp (see RUNNING.md).]"
    )
