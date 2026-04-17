"""
Wiki tools — Bella's knowledge base maintenance layer.
Sits on top of the Obsidian vault. Three tools:
  - wiki_ingest_source   : save a raw source + create/update linked wiki stubs
  - wiki_get_index       : fast read of wiki/INDEX.md + file counts per folder
  - wiki_health_check    : scan for stubs, broken links, empty sections
"""

from __future__ import annotations

import os
import re
import time
from datetime import date
from typing import TYPE_CHECKING, Any

from clients.file_read import read_utf8_or_error_message

if TYPE_CHECKING:
    from fastmcp import FastMCP
    from clients.obsidian import ObsidianClient

# Wiki folder paths (relative to vault root)
WIKI_ROOT = "wiki"
RAW_DIR = "wiki/raw"
CONCEPTS_DIR = "wiki/concepts"
PAPERS_DIR = "wiki/papers"
PROJECTS_DIR = "wiki/projects"
PEOPLE_DIR = "wiki/people"
OUTPUTS_DIR = "wiki/outputs"
INDEX_PATH = "wiki/INDEX.md"

# Starter index when the vault has no wiki yet (matches prompts that call wiki_get_index).
_STOCK_INDEX = """# Bella Wiki — Index

Compiled knowledge lives here: raw sources in `wiki/raw/`, articles in `wiki/concepts/`, `wiki/papers/`, etc. Bella uses wikilinks (`[[like this]]`) and updates this file when ingesting.

## Recent activity
_(Ingest lines are appended by `wiki_ingest_source`.)_

## Quick map
| Area | Folder |
|------|--------|
| Raw sources | `wiki/raw/` |
| Concepts | `wiki/concepts/` |
| Papers | `wiki/papers/` |
| Projects | `wiki/projects/` |
| People | `wiki/people/` |
| Outputs | `wiki/outputs/` |
| Changelog | `wiki/LOG.md` |
"""


def _ensure_wiki_layout(obsidian: "ObsidianClient") -> None:
    """Create wiki folders, INDEX.md, LOG.md, and trainee stubs if missing."""
    vault_str = str(obsidian.vault)
    folders = [
        RAW_DIR,
        CONCEPTS_DIR,
        PAPERS_DIR,
        PROJECTS_DIR,
        PEOPLE_DIR,
        OUTPUTS_DIR,
        "wiki/trainee/qanoniah",
        "wiki/trainee/rakaya",
        "wiki/trainee/moasherat",
    ]
    for rel in folders:
        os.makedirs(os.path.join(vault_str, rel), exist_ok=True)

    index_full = os.path.join(vault_str, INDEX_PATH)
    if not os.path.isfile(index_full):
        obsidian.create_note(INDEX_PATH, _STOCK_INDEX)

    log_rel = "wiki/LOG.md"
    log_full = os.path.join(vault_str, log_rel)
    if not os.path.isfile(log_full):
        obsidian.create_note(
            log_rel,
            "# Wiki changelog\n\nAppend-only log of ingests and maintenance passes.\n",
        )

    for company in ("qanoniah", "rakaya", "moasherat"):
        overview = f"wiki/trainee/{company}/overview.md"
        ov_full = os.path.join(vault_str, overview)
        if not os.path.isfile(ov_full):
            obsidian.create_note(
                overview,
                f"# {company.title()} — trainee overview\n\n_Context for trainee work; link tasks and notes here._\n",
            )


def _safe_read(path: str, retries: int = 4) -> str:
    """Read file; resilient to errno 35 on macOS Docker/Colima vault bind mounts."""
    _ = retries  # kept for callers / future tuning
    return read_utf8_or_error_message(path)


def _wiki_catalog_from_listdir(vault_str: str, max_chars: int = 14000) -> str:
    """
    Build a markdown catalog from folder listings only (no INDEX.md read).
    Survives Colima errno 35 on single-file reads when listdir still works.
    """
    lines: list[str] = [
        "# Wiki catalog (auto-generated)\n",
        "_INDEX.md could not be read from the container; this list uses directory scans only._\n\n",
    ]
    total = sum(len(x) for x in lines)
    for folder in [RAW_DIR, CONCEPTS_DIR, PAPERS_DIR, PROJECTS_DIR, PEOPLE_DIR, OUTPUTS_DIR]:
        folder_path = os.path.join(vault_str, folder)
        try:
            names = sorted(f for f in os.listdir(folder_path) if f.endswith(".md"))
        except OSError:
            continue
        block_lines = [f"## `{folder}`\n"] + [f"- `{n}`" for n in names] + ["\n"]
        block = "\n".join(block_lines)
        if total + len(block) > max_chars:
            lines.append(f"## `{folder}`\n_(truncated — catalog size cap)_\n")
            break
        lines.append(block)
        total += len(block)
    return "".join(lines)


def _today() -> str:
    return date.today().isoformat()


def _slugify(title: str) -> str:
    slug = title.lower().strip()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_]+", "-", slug)
    return slug[:60]


def register(mcp: "FastMCP", obsidian: "ObsidianClient") -> None:
    def _touch_wiki_layout() -> None:
        """Idempotent: (re)create wiki dirs + INDEX/LOG/stubs if anything is missing."""
        try:
            _ensure_wiki_layout(obsidian)
        except OSError as e:
            print(f"[Bella] Warning: wiki layout ensure failed: {e}")

    _touch_wiki_layout()

    @mcp.tool()
    def wiki_get_index() -> dict[str, Any]:
        """
        Read the wiki master index and return a summary of what exists.
        Use this at the start of any wiki-related task to understand current state.
        Returns: index content + file counts per wiki folder.
        """
        _touch_wiki_layout()
        vault_str = str(obsidian.vault)

        # Read index file with retry — handles macOS bind-mount errno 35
        index_path = os.path.join(vault_str, INDEX_PATH)
        if not os.path.isfile(index_path):
            index_content = f"Index not found at: {index_path}"
        else:
            index_content = _safe_read(index_path)
            if index_content.startswith("[READ ERROR"):
                catalog = _wiki_catalog_from_listdir(vault_str)
                err_snip = index_content.strip().replace("\n", " ")[:400]
                index_content = (
                    f"{catalog}\n---\n**Note:** INDEX.md read failed; catalog above is from "
                    f"directory listing. Raw error (truncated): {err_snip}\n"
                )

        # Count .md files per folder using os.listdir — no glob
        folder_counts: dict[str, int] = {}
        for folder in [RAW_DIR, CONCEPTS_DIR, PAPERS_DIR, PROJECTS_DIR, PEOPLE_DIR, OUTPUTS_DIR]:
            folder_path = os.path.join(vault_str, folder)
            try:
                files = [f for f in os.listdir(folder_path) if f.endswith(".md")]
                folder_counts[folder.split("/")[-1]] = len(files)
            except (FileNotFoundError, OSError):
                folder_counts[folder.split("/")[-1]] = 0

        return {
            "index": index_content,
            "file_counts": folder_counts,
            "total": sum(folder_counts.values()),
        }

    @mcp.tool()
    def wiki_ingest_source(
        title: str,
        content: str,
        source_type: str = "article",
        concepts: str = "",
    ) -> dict[str, Any]:
        """
        Save a raw source to wiki/raw/ and create a stub in the right wiki folder.

        title: Title of the source.
        content: Full content to save (markdown, article text, paper summary, etc.)
        source_type: One of: article | paper | brief | clip | note
        concepts: Comma-separated list of related concept names to backlink (e.g. "arabic-nlp, xai")

        After calling this, Bella should:
        1. Read the saved raw file
        2. Create/update the relevant wiki article (concepts/, papers/, etc.)
        3. Update wiki/INDEX.md with the new entry
        """
        _touch_wiki_layout()
        slug = _slugify(title)
        today = _today()

        # Save to raw/
        raw_path = f"{RAW_DIR}/{today}-{slug}.md"
        raw_frontmatter = f"---\ntitle: {title}\ntype: {source_type}\ndate: {today}\n---\n\n"
        try:
            obsidian.create_note(raw_path, raw_frontmatter + content)
            raw_status = "created"
        except FileExistsError:
            obsidian.append_to_note(raw_path, f"\n\n---\n*Updated {today}*\n\n" + content)
            raw_status = "appended"

        # Build concept backlinks
        concept_links = ""
        if concepts:
            links = [f"[[{c.strip()}]]" for c in concepts.split(",") if c.strip()]
            concept_links = "\n".join(f"- {l}" for l in links)

        # Create stub in appropriate folder based on source_type
        if source_type == "paper":
            stub_dir = PAPERS_DIR
            stub_content = (
                f"# {title}\n"
                f"**Date added:** {today}  \n"
                f"**Raw source:** [[{today}-{slug}]]\n\n"
                f"## One-line summary\n_Fill in._\n\n"
                f"## Key contributions\n_Fill in._\n\n"
                f"## Relevance to Yousef\n_Fill in._\n\n"
                f"## Concepts\n{concept_links or '_Add concept links._'}\n"
            )
        else:
            stub_dir = CONCEPTS_DIR if source_type in ("article", "note") else OUTPUTS_DIR
            stub_content = (
                f"# {title}\n"
                f"**Date added:** {today}  \n"
                f"**Source:** [[{today}-{slug}]]\n\n"
                f"## Summary\n_Fill in — or ask Bella to compile from raw source._\n\n"
                f"## Key ideas\n_Fill in._\n\n"
                f"## Related concepts\n{concept_links or '_Add links._'}\n"
            )

        stub_path = f"{stub_dir}/{slug}.md"
        try:
            obsidian.create_note(stub_path, stub_content)
            stub_status = "created"
        except FileExistsError:
            stub_status = "already exists — update manually or ask Bella to merge"

        # Append to index + chronological log (LLM-wiki style)
        update_line = f"\n{today} | ingested | [[{slug}]] ({source_type}) → raw + stub"
        log_line = f"\n## [{today}] ingest | {title}\n- Raw: `{raw_path}` · Stub: `{stub_path}` · type: {source_type}\n"
        for rel, extra in ((INDEX_PATH, update_line), ("wiki/LOG.md", log_line)):
            try:
                obsidian.append_to_note(rel, extra)
            except FileNotFoundError:
                _touch_wiki_layout()
                try:
                    obsidian.append_to_note(rel, extra)
                except OSError:
                    pass

        return {
            "raw_saved": raw_path,
            "raw_status": raw_status,
            "stub_path": stub_path,
            "stub_status": stub_status,
            "next_step": f"Read {raw_path}, then compile into {stub_path} and update INDEX.md",
        }

    @mcp.tool()
    def wiki_health_check() -> dict[str, Any]:
        """
        Scan the wiki for quality issues and return a report.
        Checks for:
        - Stub articles (very short, unfilled)
        - Files with no backlinks to concepts
        - Concepts mentioned in INDEX but missing as files
        - Output files older than 30 days not yet filed back

        Use weekly to keep the wiki clean and suggest new articles to write.
        """
        _touch_wiki_layout()
        issues: list[str] = []
        suggestions: list[str] = []
        stats: dict[str, Any] = {}

        vault_str = str(obsidian.vault)

        def _read_file(path: str) -> str:
            return _safe_read(path)

        def _list_md(folder: str) -> list[str]:
            """List .md file paths in a folder."""
            try:
                return [
                    os.path.join(folder, f)
                    for f in os.listdir(folder)
                    if f.endswith(".md")
                ]
            except (FileNotFoundError, OSError):
                return []

        # 1. Find stub articles (< 200 chars of actual content)
        stubs: list[str] = []
        for folder in [CONCEPTS_DIR, PAPERS_DIR, PROJECTS_DIR, PEOPLE_DIR]:
            folder_path = os.path.join(vault_str, folder)
            for fpath in _list_md(folder_path):
                text = _read_file(fpath)
                body = re.sub(r"^#.*$", "", text, flags=re.MULTILINE)
                body = re.sub(r"_Fill in.*?_", "", body)
                body = re.sub(r"\s+", " ", body).strip()
                if len(body) < 150:
                    stubs.append(os.path.relpath(fpath, vault_str))

        if stubs:
            issues.append(f"{len(stubs)} stub articles (unfilled): " + ", ".join(stubs[:5]))

        # 2. Find files with no [[wikilinks]]
        no_links: list[str] = []
        for folder in [CONCEPTS_DIR, PAPERS_DIR]:
            folder_path = os.path.join(vault_str, folder)
            for fpath in _list_md(folder_path):
                text = _read_file(fpath)
                if "[[" not in text:
                    no_links.append(os.path.relpath(fpath, vault_str))

        if no_links:
            issues.append(f"{len(no_links)} articles with no backlinks: " + ", ".join(no_links[:5]))

        # 3. Check INDEX for mentioned concepts that don't have files
        index_path = os.path.join(vault_str, INDEX_PATH)
        index_text = _read_file(index_path)
        if not os.path.isfile(index_path):
            issues.append("INDEX.md not found")
        elif index_text.startswith("[READ ERROR"):
            issues.append(f"INDEX.md unreadable (I/O): {index_text[:120]}")
        else:
            mentioned = re.findall(r"\[\[([^\]]+)\]\]", index_text)
            missing_files: list[str] = []
            for name in set(mentioned):
                slug = _slugify(name)
                found = any(
                    os.path.exists(os.path.join(vault_str, folder, f"{slug}.md")) or
                    os.path.exists(os.path.join(vault_str, folder, f"{name}.md"))
                    for folder in [CONCEPTS_DIR, PAPERS_DIR, PROJECTS_DIR, PEOPLE_DIR]
                )
                if not found:
                    missing_files.append(name)
            if missing_files:
                issues.append(f"{len(missing_files)} INDEX entries with no file: " + ", ".join(missing_files[:8]))
                for m in missing_files[:5]:
                    suggestions.append(f"Create article for: [[{m}]]")

        # 4. Count raw files not referenced in any wiki article
        raw_dir_path = os.path.join(vault_str, RAW_DIR)
        raw_files = _list_md(raw_dir_path)
        unprocessed = []
        for rf in raw_files:
            stem = os.path.splitext(os.path.basename(rf))[0]
            referenced = False
            for folder in [CONCEPTS_DIR, PAPERS_DIR, PROJECTS_DIR, OUTPUTS_DIR]:
                folder_path = os.path.join(vault_str, folder)
                for wf in _list_md(folder_path):
                    if stem in _read_file(wf):
                        referenced = True
                        break
                if referenced:
                    break
            if not referenced:
                unprocessed.append(os.path.basename(rf))
        if unprocessed:
            issues.append(f"{len(unprocessed)} raw files not yet compiled into wiki: " + ", ".join(unprocessed[:5]))
            suggestions.append("Run wiki compilation pass on unprocessed raw files")

        stats["stubs"] = len(stubs)
        stats["no_links"] = len(no_links)

        return {
            "issues": issues,
            "suggestions": suggestions,
            "stats": stats,
            "verdict": "clean" if not issues else f"{len(issues)} issues found",
        }
