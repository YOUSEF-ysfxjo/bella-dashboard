"""
Obsidian vault tools — read, search, create, update notes.
Bella can use these to access Yousef's knowledge base.
"""

from __future__ import annotations

from fastmcp import FastMCP

from clients.obsidian import ObsidianClient


def register(server: FastMCP, obsidian: ObsidianClient) -> None:

    @server.tool()
    def obsidian_read_note(path: str) -> str:
        """
        Read the full content of a note from the Obsidian vault.

        Args:
            path: Relative path to the note, e.g. 'Phase A - Word Embeddings/Word2Vec (Mikolov 2013).md'
        """
        try:
            return obsidian.read_note(path)
        except FileNotFoundError as e:
            return f"Error: {e}"

    @server.tool()
    def obsidian_list_notes(folder: str = "") -> list[dict]:
        """
        List all notes in the vault, optionally filtered to a sub-folder.

        Args:
            folder: Optional sub-folder name, e.g. 'Phase A - Word Embeddings'. Leave empty for all notes.
        """
        return obsidian.list_notes(folder)

    @server.tool()
    def obsidian_search(
        query: str,
        folder: str = "",
        max_results: int = 30,
    ) -> list[dict]:
        """
        Substring search in the Obsidian vault. **Prefer narrowing `folder`** to save time and tokens
        (e.g. `wiki`, `wiki/concepts`, `Phase A - Word Embeddings`) instead of scanning the whole vault.

        Args:
            query: Text to search for (case-insensitive substring).
            folder: Optional vault-relative folder to limit the scan. Empty = entire vault (slower, noisier).
            max_results: Stop after this many matches (default 30, max 200).
        """
        try:
            results = obsidian.search_notes(query, folder_prefix=folder, max_results=max_results)
        except (ValueError, FileNotFoundError) as e:
            return [{"error": str(e)}]
        if not results:
            scope = f" in {folder!r}" if folder else ""
            return [{"message": f"No notes found matching: {query}{scope}"}]
        return results

    @server.tool()
    def obsidian_vault_structure() -> dict:
        """
        Get an overview of the vault: total note count and notes per top-level folder.
        Useful for understanding what knowledge areas exist.
        """
        return obsidian.get_vault_structure()

    @server.tool()
    def obsidian_create_note(path: str, content: str) -> str:
        """
        Create a new note in the Obsidian vault.

        Args:
            path: Relative path including filename, e.g. 'Phase B - Contextual Embeddings/LSTM.md'
            content: Full markdown content of the note
        """
        try:
            obsidian.create_note(path, content)
            return f"Created: {path}"
        except FileExistsError as e:
            return f"Error: {e}"

    @server.tool()
    def obsidian_update_note(path: str, content: str) -> str:
        """
        Overwrite a note's content entirely.

        Args:
            path: Relative path to the note
            content: New full markdown content
        """
        try:
            obsidian.update_note(path, content)
            return f"Updated: {path}"
        except FileNotFoundError as e:
            return f"Error: {e}"

    @server.tool()
    def obsidian_append_to_note(path: str, content: str) -> str:
        """
        Append content to the end of an existing note without overwriting it.
        Good for adding new insights, references, or sections.

        Args:
            path: Relative path to the note
            content: Markdown content to append
        """
        try:
            obsidian.append_to_note(path, content)
            return f"Appended to: {path}"
        except FileNotFoundError as e:
            return f"Error: {e}"

    @server.tool()
    def obsidian_delete_note(path: str) -> str:
        """
        Delete a note from the vault.

        Args:
            path: Relative path to the note
        """
        try:
            obsidian.delete_note(path)
            return f"Deleted: {path}"
        except FileNotFoundError as e:
            return f"Error: {e}"
