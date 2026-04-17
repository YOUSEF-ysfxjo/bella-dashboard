"""
GitHub MCP tools — registered on the FastMCP server.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from fastmcp import FastMCP
    from clients.github import GitHubClient


def register(mcp: "FastMCP", github: "GitHubClient") -> None:
    """Register all GitHub tools on the MCP server."""

    @mcp.tool()
    def github_list_repos(
        visibility: str = "all",
        sort: str = "updated",
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """
        List all GitHub repos for the authenticated user.
        visibility: "all", "public", or "private"
        sort: "created", "updated", "pushed", "full_name"
        limit: Max number of repos to return.
        """
        return github.list_repos(visibility=visibility, sort=sort, limit=limit)

    @mcp.tool()
    def github_get_repo(owner: str, repo: str) -> dict[str, Any]:
        """
        Get detailed info about a specific repo.
        owner: GitHub username or org (e.g. "YOUSEF-ysfxjo")
        repo: Repo name (e.g. "text-complaint-api")
        Returns: stars, forks, open issues, topics, language, URLs, etc.
        """
        return github.get_repo(owner, repo)

    @mcp.tool()
    def github_get_readme(owner: str, repo: str) -> str:
        """
        Fetch the README of a repo as plain text.
        Useful for understanding what a project is about.
        """
        return github.get_readme(owner, repo)

    @mcp.tool()
    def github_list_issues(
        owner: str,
        repo: str,
        state: str = "open",
        labels: str = "",
        limit: int = 30,
    ) -> list[dict[str, Any]]:
        """
        List issues for a repo (excludes pull requests).
        state: "open", "closed", or "all"
        labels: Comma-separated label names to filter by (e.g. "bug,enhancement")
        limit: Max results.
        """
        label_list = [l.strip() for l in labels.split(",") if l.strip()] if labels else None
        return github.list_issues(owner, repo, state=state, labels=label_list, limit=limit)

    @mcp.tool()
    def github_get_issue(owner: str, repo: str, number: int) -> dict[str, Any]:
        """
        Get full details of a specific issue including its comment thread.
        number: Issue number (e.g. 42)
        """
        return github.get_issue(owner, repo, number)

    @mcp.tool()
    def github_create_issue(
        owner: str,
        repo: str,
        title: str,
        body: str = "",
        labels: str = "",
    ) -> dict[str, Any]:
        """
        Open a new issue in a repo.
        body: Issue description in markdown.
        labels: Comma-separated label names (must exist in the repo).
        """
        label_list = [l.strip() for l in labels.split(",") if l.strip()] if labels else None
        return github.create_issue(
            owner, repo, title,
            body=body if body else None,
            labels=label_list,
        )

    @mcp.tool()
    def github_list_commits(
        owner: str,
        repo: str,
        branch: str = "",
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """
        Get recent commits for a repo.
        branch: Branch name (empty = default branch).
        limit: Number of commits to return.
        Returns: sha (short), commit message (first line), author, date, URL.
        """
        return github.list_commits(owner, repo, branch=branch if branch else None, limit=limit)

    @mcp.tool()
    def github_get_file(
        owner: str,
        repo: str,
        path: str,
        branch: str = "",
    ) -> dict[str, Any]:
        """
        Read a specific file from a repo.
        path: File path relative to repo root (e.g. "src/main.py" or "README.md")
        branch: Branch name (empty = default branch).
        Returns: decoded file content as text.
        """
        return github.get_file(owner, repo, path, branch=branch if branch else None)

    @mcp.tool()
    def github_search_code(
        query: str,
        repo: str = "",
        limit: int = 15,
    ) -> list[dict[str, Any]]:
        """
        Search code across GitHub.
        query: Search terms (e.g. "FedAvg federated learning")
        repo: Scope to a specific repo in "owner/repo" format (empty = all your repos).
        Returns: file paths + URLs where the code was found.
        """
        return github.search_code(query, repo=repo if repo else None, limit=limit)

    @mcp.tool()
    def github_list_prs(
        owner: str,
        repo: str,
        state: str = "open",
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """
        List pull requests for a repo.
        state: "open", "closed", or "all"
        """
        return github.list_prs(owner, repo, state=state, limit=limit)

    @mcp.tool()
    def github_write_file(
        owner: str,
        repo: str,
        path: str,
        content: str,
        message: str,
        branch: str = "",
    ) -> dict[str, Any]:
        """
        Create or update a file in a GitHub repo (makes a commit).
        If the file exists it's updated; if not it's created.

        owner: GitHub username (e.g. "YOUSEF-ysfxjo")
        repo: Repo name (e.g. "text-complaint-api")
        path: File path in repo (e.g. "src/utils.py", "README.md")
        content: Full file content as text
        message: Commit message
        branch: Branch to commit to (empty = default branch)
        """
        return github.create_or_update_file(
            owner, repo, path, content, message,
            branch=branch if branch else None,
        )

    @mcp.tool()
    def github_delete_file(
        owner: str,
        repo: str,
        path: str,
        message: str,
        branch: str = "",
    ) -> dict[str, Any]:
        """Delete a file from a GitHub repo (makes a commit)."""
        return github.delete_file(
            owner, repo, path, message,
            branch=branch if branch else None,
        )

    @mcp.tool()
    def github_create_branch(
        owner: str,
        repo: str,
        branch: str,
        from_branch: str = "",
    ) -> dict[str, Any]:
        """
        Create a new branch in a repo.
        from_branch: Source branch (empty = default branch).
        """
        return github.create_branch(
            owner, repo, branch,
            from_branch=from_branch if from_branch else None,
        )

    @mcp.tool()
    def github_list_branches(owner: str, repo: str) -> list[str]:
        """List all branches in a repo."""
        return github.list_branches(owner, repo)

    @mcp.tool()
    def github_get_diff(
        owner: str,
        repo: str,
        base: str,
        head: str,
    ) -> dict[str, Any]:
        """
        Get the diff between two branches or commits.
        Returns files changed with their patches.
        Example: github_get_diff("YOUSEF-ysfxjo", "text-complaint-api", "main", "dev")
        """
        return github.get_diff(owner, repo, base, head)
