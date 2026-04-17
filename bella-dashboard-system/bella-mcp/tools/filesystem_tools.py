"""
File system MCP tools — read, write, edit, list any file/directory.
Mac paths are mounted into Docker:
  ~/Desktop/projects → /app/projects
  ~/ (home)          → /app/home
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from fastmcp import FastMCP
    from clients.filesystem import FilesystemClient


def register(mcp: "FastMCP", fs: "FilesystemClient") -> None:

    @mcp.tool()
    def fs_read(path: str) -> str:
        """
        Read a file's full text content.
        path: Absolute path — use container paths (/app/projects/...) or
              host paths (/Users/yousef/Desktop/projects/...) — both work.

        Examples:
        - fs_read("/app/projects/text-complaint-api/main.py")
        - fs_read("/app/projects/bella-system/bella-mcp/system_prompt.txt")
        - fs_read("/app/home/.zshrc")
        """
        return fs.read(path)

    @mcp.tool()
    def fs_write(path: str, content: str) -> dict[str, Any]:
        """
        Write content to a file (full overwrite). Creates parent directories if needed.
        Use fs_edit() for targeted changes — use this only for new files or full rewrites.

        path: Target file path.
        content: Full file content to write.
        """
        return fs.write(path, content)

    @mcp.tool()
    def fs_edit(path: str, old_string: str, new_string: str) -> dict[str, Any]:
        """
        Replace old_string with new_string in a file (exact string replacement).
        old_string must appear exactly ONCE in the file — include enough context to make it unique.
        This is the preferred way to edit existing files (like Claude Code's Edit tool).

        Examples:
        - fs_edit("/app/projects/api/main.py", "def old_name(", "def new_name(")
        - fs_edit("/app/projects/api/config.py", 'DEBUG = True', 'DEBUG = False')
        """
        return fs.edit(path, old_string, new_string)

    @mcp.tool()
    def fs_append(path: str, content: str) -> dict[str, Any]:
        """
        Append content to a file. Creates file if it doesn't exist.
        Good for adding entries to logs, notes, or config files.
        """
        return fs.append(path, content)

    @mcp.tool()
    def fs_delete(path: str) -> dict[str, Any]:
        """Delete a file permanently."""
        return fs.delete(path)

    @mcp.tool()
    def fs_list(path: str, recursive: bool = False) -> list[dict[str, Any]]:
        """
        List a directory's contents. Returns name, path, type (file/dir), size.
        recursive: Set True to list all nested files (caution: can be large).

        Examples:
        - fs_list("/app/projects")  → see all projects
        - fs_list("/app/projects/text-complaint-api")  → see project files
        - fs_list("/app/projects/text-complaint-api", recursive=True)  → full tree
        """
        return fs.list_dir(path, recursive=recursive)

    @mcp.tool()
    def fs_find(pattern: str, base: str = "") -> list[str]:
        """
        Find files by glob pattern.
        pattern: Glob pattern relative to base (e.g. "**/*.py", "*.md", "src/**/*.ts").
        base: Base directory (default: /app/projects).

        Examples:
        - fs_find("**/*.py", "/app/projects/text-complaint-api")
        - fs_find("**/requirements*.txt")
        - fs_find("**/.env*")
        """
        return fs.find(pattern, base=base)

    @mcp.tool()
    def fs_exists(path: str) -> bool:
        """Check if a file or directory exists at the given path."""
        return fs.exists(path)

    @mcp.tool()
    def fs_count(path: str, extension: str = "") -> dict[str, Any]:
        """
        Count files in a directory WITHOUT listing them — safe for large folders.
        Use this instead of fs_list when you only need a count (avoids context overflow).

        path: Directory to count files in.
        extension: Optional filter e.g. ".md", ".py", ".json". Empty = count all files.

        Returns total count + per-subfolder breakdown.

        Examples:
        - fs_count("/app/projects/Qanoniah-tasks/embedding-models-extractions/legal_benchmark/markdown")
        - fs_count("/app/projects/Qanoniah-tasks/embedding-models-extractions/legal_benchmark/markdown", ".md")
        """
        from clients.filesystem import _resolve
        resolved = str(_resolve(path))
        if not os.path.isdir(resolved):
            return {"error": f"Not a directory: {path}"}

        total = 0
        breakdown: dict[str, int] = {}

        for entry in os.scandir(resolved):
            if entry.is_dir(follow_symlinks=False):
                count = 0
                for root, _, files in os.walk(entry.path):
                    for fname in files:
                        if not extension or fname.endswith(extension):
                            count += 1
                breakdown[entry.name] = count
                total += count
            elif entry.is_file():
                if not extension or entry.name.endswith(extension):
                    total += 1
                    breakdown["_root"] = breakdown.get("_root", 0) + 1

        return {"path": path, "total": total, "extension_filter": extension or "all", "by_subfolder": breakdown}
