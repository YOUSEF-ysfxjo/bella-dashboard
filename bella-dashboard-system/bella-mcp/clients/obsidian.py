"""
Obsidian vault client — file-system access to the vault.
Uses os.walk + safe open() instead of pathlib.rglob to avoid
macOS Docker bind-mount errno 35 deadlocks.
"""

from __future__ import annotations

import os
import time
from typing import Any

from clients.file_read import read_utf8_resilient

# Cap matches returned (full vault scan can be huge; keeps tool responses small).
_DEFAULT_SEARCH_MAX = int(os.environ.get("BELLA_OBSIDIAN_SEARCH_MAX_RESULTS", "30"))


def _safe_read(path: str, retries: int = 4) -> str:
    """Read a file; resilient to errno 35 on macOS Docker/Colima bind mounts."""
    _ = retries
    return read_utf8_resilient(path)


def _walk_md(root: str) -> list[str]:
    """Return all .md file paths under root using os.walk (no pathlib)."""
    results: list[str] = []
    try:
        for dirpath, _, filenames in os.walk(root):
            for fname in sorted(filenames):
                if fname.lower().endswith(".md"):
                    results.append(os.path.join(dirpath, fname))
    except OSError:
        pass
    return results


class ObsidianClient:
    def __init__(self) -> None:
        vault_path = os.environ.get("OBSIDIAN_VAULT_PATH", "")
        if not vault_path:
            raise RuntimeError("OBSIDIAN_VAULT_PATH is not set")
        self.vault_str: str = vault_path.rstrip("/")
        if not os.path.isdir(self.vault_str):
            raise RuntimeError(f"Vault path does not exist: {vault_path}")
        # Keep self.vault as a string (no pathlib) to avoid bind-mount issues
        self.vault = self.vault_str  # type: ignore[assignment]

    def _full(self, rel_path: str) -> str:
        return os.path.join(self.vault_str, rel_path)

    def _resolved_subdir(self, folder_rel: str) -> str:
        """Resolve a vault-relative folder; reject path traversal."""
        if not folder_rel or not folder_rel.strip():
            return self.vault_str
        joined = os.path.normpath(os.path.join(self.vault_str, folder_rel.strip().lstrip("/")))
        vault_norm = os.path.normpath(self.vault_str)
        if joined != vault_norm and not joined.startswith(vault_norm + os.sep):
            raise ValueError(f"Folder escapes vault: {folder_rel!r}")
        if not os.path.isdir(joined):
            raise FileNotFoundError(f"Not a folder in vault: {folder_rel}")
        return joined

    # ──────────────────────────────────────────────
    # Read
    # ──────────────────────────────────────────────

    def read_note(self, path: str) -> str:
        full = self._full(path)
        if not os.path.isfile(full):
            raise FileNotFoundError(f"Note not found: {path}")
        content = _safe_read(full)
        if not content and os.path.isfile(full):
            raise OSError(f"Could not read note (bind-mount issue?): {path}")
        return content

    def list_notes(self, folder: str = "") -> list[dict[str, str]]:
        """List all .md notes, optionally under a sub-folder."""
        base = self._full(folder) if folder else self.vault_str
        results = []
        for fpath in _walk_md(base):
            rel = os.path.relpath(fpath, self.vault_str)
            name = os.path.splitext(os.path.basename(fpath))[0]
            results.append({"path": rel, "name": name})
        return results

    def search_notes(
        self,
        query: str,
        folder_prefix: str = "",
        max_results: int | None = None,
    ) -> list[dict[str, Any]]:
        """
        Substring search under the vault or a single subfolder (much cheaper when folder_prefix is set).
        """
        cap = max_results if max_results is not None else _DEFAULT_SEARCH_MAX
        cap = max(1, min(cap, 200))

        if folder_prefix.strip():
            root = self._resolved_subdir(folder_prefix)
        else:
            root = self.vault_str

        query_lower = query.lower()
        results: list[dict[str, Any]] = []
        for fpath in _walk_md(root):
            if len(results) >= cap:
                break
            text = _safe_read(fpath)
            if not text:
                continue
            if query_lower in text.lower():
                snippet = ""
                for line in text.splitlines():
                    if query_lower in line.lower():
                        snippet = line.strip()[:200]
                        break
                rel = os.path.relpath(fpath, self.vault_str)
                name = os.path.splitext(os.path.basename(fpath))[0]
                results.append({"path": rel, "name": name, "snippet": snippet})
        return results

    # ──────────────────────────────────────────────
    # Write
    # ──────────────────────────────────────────────

    def create_note(self, path: str, content: str) -> str:
        full = self._full(path)
        if os.path.exists(full):
            raise FileExistsError(f"Note already exists: {path}")
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w", encoding="utf-8") as f:
            f.write(content)
        return str(path)

    def update_note(self, path: str, content: str) -> str:
        full = self._full(path)
        if not os.path.isfile(full):
            raise FileNotFoundError(f"Note not found: {path}")
        with open(full, "w", encoding="utf-8") as f:
            f.write(content)
        return str(path)

    def append_to_note(self, path: str, content: str) -> str:
        full = self._full(path)
        if not os.path.isfile(full):
            raise FileNotFoundError(f"Note not found: {path}")
        existing = _safe_read(full)
        separator = "\n" if existing.endswith("\n") else "\n\n"
        with open(full, "w", encoding="utf-8") as f:
            f.write(existing + separator + content)
        return str(path)

    def delete_note(self, path: str) -> str:
        full = self._full(path)
        if not os.path.isfile(full):
            raise FileNotFoundError(f"Note not found: {path}")
        os.unlink(full)
        return str(path)

    # ──────────────────────────────────────────────
    # Helpers
    # ──────────────────────────────────────────────

    def get_vault_structure(self) -> dict[str, Any]:
        """Return top-level folder and file counts."""
        folders: dict[str, int] = {}
        for fpath in _walk_md(self.vault_str):
            rel = os.path.relpath(fpath, self.vault_str)
            parts = rel.split(os.sep)
            top = parts[0] if len(parts) > 1 else "_root"
            folders[top] = folders.get(top, 0) + 1
        return {"total_notes": sum(folders.values()), "folders": folders}
