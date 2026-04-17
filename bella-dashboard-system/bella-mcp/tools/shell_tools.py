"""
Shell execution MCP tools — run commands and Python code.
Commands execute inside the Docker container with Mac project files mounted.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from fastmcp import FastMCP
    from clients.shell import ShellClient


def register(mcp: "FastMCP", shell: "ShellClient") -> None:

    @mcp.tool()
    def shell_run(
        command: str,
        cwd: str = "",
        timeout: int = 60,
    ) -> dict[str, Any]:
        """
        Run any shell command. Returns stdout, stderr, exit_code.

        cwd: Working directory (default: /app/projects which is ~/Desktop/projects on host).
             Use full container paths like /app/projects/text-complaint-api
             or host-style paths like /Users/yousef/Desktop/projects/text-complaint-api (auto-translated).
        timeout: Max seconds to wait (default 60, max 300).

        Examples:
        - shell_run("ls -la")
        - shell_run("git log --oneline -10", cwd="/app/projects/text-complaint-api")
        - shell_run("python -m pytest tests/", cwd="/app/projects/text-complaint-api")
        - shell_run("git status && git diff --stat")
        - shell_run("cat pyproject.toml", cwd="/app/projects/bella-dashboard/bella-dashboard-system/bella-mcp")
        """
        return shell.run(command, cwd=cwd if cwd else None, timeout=timeout)

    @mcp.tool()
    def shell_python(
        code: str,
        timeout: int = 60,
    ) -> dict[str, Any]:
        """
        Execute a Python code snippet and return its output.
        Useful for quick calculations, data analysis, or testing logic.

        code: Full Python code to execute (as a string).
        timeout: Max seconds (default 60).

        Example:
        shell_python("import json; data = {'x': 1}; print(json.dumps(data, indent=2))")
        """
        return shell.run_python(code, timeout=timeout)

    @mcp.tool()
    def shell_git(
        repo_path: str,
        args: str,
    ) -> dict[str, Any]:
        """
        Run a git command in a specific repo directory.
        repo_path: Path to the repo (container path or host path).
        args: Git subcommand and flags, e.g. "log --oneline -10" or "status" or "diff HEAD".

        Examples:
        - shell_git("/app/projects/text-complaint-api", "log --oneline -5")
        - shell_git("/app/projects/bella-dashboard", "status")
        - shell_git("/app/projects/complaint-xai-fl-research", "diff --stat HEAD~1")
        """
        return shell.run(f"git {args}", cwd=repo_path)
