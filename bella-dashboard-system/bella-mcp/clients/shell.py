"""
Shell execution client — runs commands inside the Docker container.
Projects directory is mounted at /app/projects (→ ~/Desktop/projects on host).
Home directory is mounted at /app/home (→ /Users/yousef on host).
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from typing import Any


DEFAULT_CWD = os.environ.get("PROJECTS_PATH", "/app/projects")


class ShellClient:
    def __init__(self) -> None:
        self.default_cwd = DEFAULT_CWD

    def run(
        self,
        command: str,
        cwd: str | None = None,
        timeout: int = 60,
        env_extra: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """
        Run a shell command. Returns stdout, stderr, exit_code, and cwd used.
        Timeout in seconds (default 60, max 300).
        """
        timeout = min(timeout, 300)
        work_dir = cwd if cwd else self.default_cwd

        # Ensure working directory exists
        if not os.path.exists(work_dir):
            work_dir = self.default_cwd

        env = os.environ.copy()
        if env_extra:
            env.update(env_extra)

        try:
            result = subprocess.run(
                command,
                shell=True,
                cwd=work_dir,
                capture_output=True,
                text=True,
                timeout=timeout,
                env=env,
            )
            return {
                "stdout": result.stdout,
                "stderr": result.stderr,
                "exit_code": result.returncode,
                "cwd": work_dir,
                "command": command,
            }
        except subprocess.TimeoutExpired:
            return {
                "stdout": "",
                "stderr": f"Command timed out after {timeout}s",
                "exit_code": -1,
                "cwd": work_dir,
                "command": command,
            }
        except Exception as e:
            return {
                "stdout": "",
                "stderr": str(e),
                "exit_code": -1,
                "cwd": work_dir,
                "command": command,
            }

    def run_python(self, code: str, timeout: int = 60) -> dict[str, Any]:
        """
        Execute a Python code snippet. Writes to a temp file and runs it.
        Uses the system Python (python3).
        """
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8"
        ) as f:
            f.write(code)
            tmp_path = f.name

        try:
            result = self.run(
                f"{sys.executable} {tmp_path}",
                cwd=self.default_cwd,
                timeout=timeout,
            )
            result["code"] = code
            return result
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
