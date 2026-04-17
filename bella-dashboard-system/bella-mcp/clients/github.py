"""
GitHub API client.
Uses PyGithub for typed access + raw requests for search endpoints.
"""

from __future__ import annotations

import base64
import os
from typing import Any

from github import Github, GithubException
from github.Repository import Repository


class GitHubClient:
    def __init__(self) -> None:
        token = os.environ.get("GITHUB_TOKEN", "")
        if not token:
            raise RuntimeError("GITHUB_TOKEN is not set")
        self._gh = Github(token)
        self._username = os.environ.get("GITHUB_USERNAME", "")

    def _user(self):
        return self._gh.get_user(self._username) if self._username else self._gh.get_user()

    def _repo(self, owner: str, repo: str) -> Repository:
        return self._gh.get_repo(f"{owner}/{repo}")

    # ──────────────────────────────────────────────
    # Repos
    # ──────────────────────────────────────────────

    def list_repos(
        self,
        visibility: str = "all",
        sort: str = "updated",
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """
        List repos for the authenticated user.
        visibility: "all", "public", "private"
        sort: "created", "updated", "pushed", "full_name"
        """
        user = self._user()
        repos = user.get_repos(visibility=visibility, sort=sort)
        results = []
        for i, r in enumerate(repos):
            if i >= limit:
                break
            results.append(self._repo_summary(r))
        return results  

    def get_repo(self, owner: str, repo: str) -> dict[str, Any]:
        r = self._repo(owner, repo)
        return self._repo_detail(r)

    @staticmethod
    def _repo_summary(r: Repository) -> dict[str, Any]:
        return {
            "name": r.name,
            "full_name": r.full_name,
            "description": r.description,
            "private": r.private,
            "language": r.language,
            "stars": r.stargazers_count,
            "updated_at": r.updated_at.isoformat() if r.updated_at else None,
            "url": r.html_url,
        }

    @staticmethod
    def _repo_detail(r: Repository) -> dict[str, Any]:
        return {
            "name": r.name,
            "full_name": r.full_name,
            "description": r.description,
            "private": r.private,
            "language": r.language,
            "stars": r.stargazers_count,
            "forks": r.forks_count,
            "open_issues": r.open_issues_count,
            "default_branch": r.default_branch,
            "topics": r.get_topics(),
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "updated_at": r.updated_at.isoformat() if r.updated_at else None,
            "pushed_at": r.pushed_at.isoformat() if r.pushed_at else None,
            "url": r.html_url,
            "clone_url": r.clone_url,
        }

    # ──────────────────────────────────────────────
    # README
    # ──────────────────────────────────────────────

    def get_readme(self, owner: str, repo: str) -> str:
        """Return decoded README content as plain text."""
        r = self._repo(owner, repo)
        try:
            readme = r.get_readme()
            return base64.b64decode(readme.content).decode("utf-8")
        except GithubException:
            return ""

    # ──────────────────────────────────────────────
    # Issues & PRs
    # ──────────────────────────────────────────────

    def list_issues(
        self,
        owner: str,
        repo: str,
        state: str = "open",
        labels: list[str] | None = None,
        limit: int = 30,
    ) -> list[dict[str, Any]]:
        """state: "open", "closed", "all". Excludes pull requests."""
        r = self._repo(owner, repo)
        kwargs: dict[str, Any] = {"state": state}
        if labels:
            kwargs["labels"] = [r.get_label(lbl) for lbl in labels]
        issues = r.get_issues(**kwargs)
        results = []
        for i, issue in enumerate(issues):
            if i >= limit:
                break
            if issue.pull_request:
                continue  # skip PRs from issues list
            results.append(self._issue_summary(issue))
        return results

    def get_issue(self, owner: str, repo: str, number: int) -> dict[str, Any]:
        r = self._repo(owner, repo)
        issue = r.get_issue(number)
        comments = [
            {
                "author": c.user.login if c.user else None,
                "body": c.body,
                "created_at": c.created_at.isoformat(),
            }
            for c in issue.get_comments()
        ]
        return {**self._issue_summary(issue), "body": issue.body, "comments": comments}

    def create_issue(
        self,
        owner: str,
        repo: str,
        title: str,
        body: str | None = None,
        labels: list[str] | None = None,
    ) -> dict[str, Any]:
        r = self._repo(owner, repo)
        kwargs: dict[str, Any] = {"title": title}
        if body:
            kwargs["body"] = body
        if labels:
            kwargs["labels"] = labels
        issue = r.create_issue(**kwargs)
        return self._issue_summary(issue)

    @staticmethod
    def _issue_summary(issue) -> dict[str, Any]:
        return {
            "number": issue.number,
            "title": issue.title,
            "state": issue.state,
            "author": issue.user.login if issue.user else None,
            "labels": [lbl.name for lbl in issue.labels],
            "created_at": issue.created_at.isoformat() if issue.created_at else None,
            "updated_at": issue.updated_at.isoformat() if issue.updated_at else None,
            "url": issue.html_url,
        }

    # ──────────────────────────────────────────────
    # Commits
    # ──────────────────────────────────────────────

    def list_commits(
        self,
        owner: str,
        repo: str,
        branch: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        r = self._repo(owner, repo)
        kwargs: dict[str, Any] = {}
        if branch:
            kwargs["sha"] = branch
        commits = r.get_commits(**kwargs)
        results = []
        for i, c in enumerate(commits):
            if i >= limit:
                break
            results.append({
                "sha": c.sha[:8],
                "message": c.commit.message.split("\n")[0],  # first line only
                "author": c.commit.author.name if c.commit.author else None,
                "date": c.commit.author.date.isoformat() if c.commit.author else None,
                "url": c.html_url,
            })
        return results

    # ──────────────────────────────────────────────
    # Files
    # ──────────────────────────────────────────────

    def get_file(
        self,
        owner: str,
        repo: str,
        path: str,
        branch: str | None = None,
    ) -> dict[str, Any]:
        """Read a file from a repo. Returns decoded content + metadata."""
        r = self._repo(owner, repo)
        kwargs: dict[str, Any] = {"path": path}
        if branch:
            kwargs["ref"] = branch
        try:
            content = r.get_contents(**kwargs)
            if isinstance(content, list):
                # it's a directory listing
                return {"type": "directory", "entries": [f.path for f in content]}
            decoded = base64.b64decode(content.content).decode("utf-8")
            return {
                "path": content.path,
                "size": content.size,
                "sha": content.sha,
                "content": decoded,
                "url": content.html_url,
            }
        except GithubException as e:
            return {"error": str(e)}

    def create_or_update_file(
        self,
        owner: str,
        repo: str,
        path: str,
        content: str,
        message: str,
        branch: str | None = None,
    ) -> dict[str, Any]:
        """Create a new file or update an existing one (commit directly to repo)."""
        import base64 as b64
        r = self._repo(owner, repo)
        encoded = b64.b64encode(content.encode("utf-8")).decode("ascii")
        kwargs: dict[str, Any] = {
            "path": path,
            "message": message,
            "content": encoded,
        }
        if branch:
            kwargs["branch"] = branch
        # Check if file exists (need SHA to update)
        try:
            existing = r.get_contents(path, ref=branch or r.default_branch)
            if isinstance(existing, list):
                return {"error": "Path is a directory"}
            kwargs["sha"] = existing.sha
            result = r.update_file(**kwargs)
            action = "updated"
        except GithubException:
            result = r.create_file(**kwargs)
            action = "created"
        return {
            "action": action,
            "path": path,
            "commit_sha": result["commit"].sha,
            "commit_url": result["commit"].html_url,
        }

    def delete_file(
        self,
        owner: str,
        repo: str,
        path: str,
        message: str,
        branch: str | None = None,
    ) -> dict[str, Any]:
        """Delete a file from a repo (commits the deletion)."""
        r = self._repo(owner, repo)
        kwargs: dict[str, Any] = {"path": path}
        if branch:
            kwargs["ref"] = branch
        existing = r.get_contents(**kwargs)
        if isinstance(existing, list):
            return {"error": "Path is a directory"}
        del_kwargs: dict[str, Any] = {
            "path": path,
            "message": message,
            "sha": existing.sha,
        }
        if branch:
            del_kwargs["branch"] = branch
        result = r.delete_file(**del_kwargs)
        return {
            "action": "deleted",
            "path": path,
            "commit_sha": result["commit"].sha,
        }

    def create_branch(
        self,
        owner: str,
        repo: str,
        branch: str,
        from_branch: str | None = None,
    ) -> dict[str, Any]:
        """Create a new branch from an existing one (default: default branch)."""
        r = self._repo(owner, repo)
        source = from_branch or r.default_branch
        source_ref = r.get_branch(source)
        r.create_git_ref(ref=f"refs/heads/{branch}", sha=source_ref.commit.sha)
        return {"branch": branch, "from": source, "sha": source_ref.commit.sha}

    def list_branches(self, owner: str, repo: str) -> list[str]:
        """List all branches in a repo."""
        r = self._repo(owner, repo)
        return [b.name for b in r.get_branches()]

    def get_diff(
        self,
        owner: str,
        repo: str,
        base: str,
        head: str,
    ) -> dict[str, Any]:
        """Get the diff between two branches or commits."""
        r = self._repo(owner, repo)
        comparison = r.compare(base, head)
        files = [
            {
                "filename": f.filename,
                "status": f.status,
                "additions": f.additions,
                "deletions": f.deletions,
                "patch": f.patch or "",
            }
            for f in comparison.files
        ]
        return {
            "base": base,
            "head": head,
            "ahead_by": comparison.ahead_by,
            "behind_by": comparison.behind_by,
            "files_changed": len(files),
            "files": files,
        }

    # ──────────────────────────────────────────────
    # Search
    # ──────────────────────────────────────────────

    def search_code(
        self, query: str, repo: str | None = None, limit: int = 15
    ) -> list[dict[str, Any]]:
        """
        Search code. If repo provided, scopes to that repo.
        repo format: "owner/repo"
        """
        q = query
        if repo:
            q = f"{query} repo:{repo}"
        results_iter = self._gh.search_code(q)
        results = []
        for i, item in enumerate(results_iter):
            if i >= limit:
                break
            results.append({
                "repo": item.repository.full_name,
                "path": item.path,
                "url": item.html_url,
                "name": item.name,
            })
        return results

    # ──────────────────────────────────────────────
    # Pull Requests
    # ──────────────────────────────────────────────

    def list_prs(
        self,
        owner: str,
        repo: str,
        state: str = "open",
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        r = self._repo(owner, repo)
        prs = r.get_pulls(state=state, sort="updated", direction="desc")
        results = []
        for i, pr in enumerate(prs):
            if i >= limit:
                break
            results.append({
                "number": pr.number,
                "title": pr.title,
                "state": pr.state,
                "author": pr.user.login if pr.user else None,
                "base": pr.base.ref,
                "head": pr.head.ref,
                "draft": pr.draft,
                "created_at": pr.created_at.isoformat() if pr.created_at else None,
                "url": pr.html_url,
            })
        return results
