"""
File system client — read/write any file on mounted paths.
Host paths are mounted into Docker:
  /Users/yousef/Desktop/projects → /app/projects
  /Users/yousef               → /app/home
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any


# Resolve host-style paths to container-mounted paths
_PATH_MAP = {
    "/Users/yousef/Desktop/projects": os.environ.get("PROJECTS_PATH", "/app/projects"),
    "/Users/yousef": os.environ.get("HOME_PATH", "/app/home"),
}


def _resolve(path: str) -> Path:
    """Translate host-style absolute paths to container paths if needed."""
    for host_prefix, container_prefix in _PATH_MAP.items():
        if path.startswith(host_prefix):
            path = container_prefix + path[len(host_prefix):]
            break
    return Path(path)


class FilesystemClient:
    def read(self, path: str) -> str:
        """Read a file's full text content."""
        p = _resolve(path)
        if not p.exists():
            raise FileNotFoundError(f"File not found: {path}")
        return p.read_text(encoding="utf-8", errors="replace")

    def write(self, path: str, content: str) -> dict[str, Any]:
        """Write content to a file (overwrites). Creates parent dirs if needed."""
        p = _resolve(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return {"path": str(p), "bytes": len(content.encode("utf-8"))}

    def edit(self, path: str, old_string: str, new_string: str) -> dict[str, Any]:
        """
        Replace the first occurrence of old_string with new_string in a file.
        Raises ValueError if old_string not found or is not unique.
        """
        p = _resolve(path)
        if not p.exists():
            raise FileNotFoundError(f"File not found: {path}")
        content = p.read_text(encoding="utf-8")
        count = content.count(old_string)
        if count == 0:
            raise ValueError(f"old_string not found in {path}")
        if count > 1:
            raise ValueError(
                f"old_string matches {count} times — provide more context to make it unique"
            )
        new_content = content.replace(old_string, new_string, 1)
        p.write_text(new_content, encoding="utf-8")
        return {"path": str(p), "replaced": 1}

    def append(self, path: str, content: str) -> dict[str, Any]:
        """Append content to a file. Creates file if it doesn't exist."""
        p = _resolve(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        existing = p.read_text(encoding="utf-8") if p.exists() else ""
        sep = "\n" if existing and not existing.endswith("\n") else ""
        p.write_text(existing + sep + content, encoding="utf-8")
        return {"path": str(p)}

    def delete(self, path: str) -> dict[str, Any]:
        """Delete a file."""
        p = _resolve(path)
        if not p.exists():
            raise FileNotFoundError(f"File not found: {path}")
        p.unlink()
        return {"deleted": str(p)}

    def list_dir(self, path: str, recursive: bool = False) -> list[dict[str, Any]]:
        """List directory contents. Set recursive=True for full tree."""
        p = _resolve(path)
        if not p.exists():
            raise FileNotFoundError(f"Directory not found: {path}")
        if not p.is_dir():
            raise NotADirectoryError(f"Not a directory: {path}")

        results = []
        iterator = p.rglob("*") if recursive else p.iterdir()
        for item in sorted(iterator):
            # Skip hidden files and common noise
            if any(part.startswith(".") for part in item.parts if part != "."):
                continue
            if item.name in {"__pycache__", "node_modules", ".git"}:
                continue
            results.append({
                "name": item.name,
                "path": str(item),
                "type": "dir" if item.is_dir() else "file",
                "size": item.stat().st_size if item.is_file() else None,
            })
        return results

    def find(self, pattern: str, base: str = "") -> list[str]:
        """Find files matching a glob pattern. base defaults to /app/projects."""
        base_path = _resolve(base) if base else Path(
            os.environ.get("PROJECTS_PATH", "/app/projects")
        )
        return [str(p) for p in sorted(base_path.glob(pattern))]

    def exists(self, path: str) -> bool:
        return _resolve(path).exists()
