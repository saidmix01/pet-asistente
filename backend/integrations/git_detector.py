"""
Git Detector — detects git repositories and active branches the user is working on.
Processes recent commits and branches to enrich the daily report.
"""

import subprocess
import os
import sys
from pathlib import Path
from typing import Any
from services.logger import info, warning, error

# Common project directories to scan for git repos
SCAN_PATHS: list[str] = []
home = Path.home()

# Cross-platform defaults
if sys.platform == "win32":
    SCAN_PATHS = [
        str(home / "Projects"),
        str(home / "projects"),
        str(home / "code"),
        str(home / "source"),
        str(home / "repos"),
        str(home / "Documents"),
        str(home / "Desktop"),
        "C:\\Projects",
        "C:\\code",
        "D:\\Projects",
        "D:\\code",
    ]
elif sys.platform == "darwin":
    SCAN_PATHS = [
        str(home / "Projects"),
        str(home / "projects"),
        str(home / "code"),
        str(home / "Code"),
        str(home / "work"),
        str(home / "Work"),
        str(home / "Documents"),
        str(home / "Desktop"),
        "/Volumes/DATOS/Proyectos",
    ]
else:  # Linux
    SCAN_PATHS = [
        str(home / "Projects"),
        str(home / "projects"),
        str(home / "code"),
        str(home / "Code"),
        str(home / "work"),
        str(home / "Work"),
        str(home / "Documents"),
        str(home / "Desktop"),
        str(home / "git"),
        str(home / "dev"),
    ]


class GitDetector:
    """
    Scans common project directories for git repos and detects
    current branches and recent commits.
    """

    def __init__(self, max_depth: int = 4) -> None:
        self._findings: list[dict] = []
        self._scan_paths = SCAN_PATHS
        self._max_depth = max_depth

    # ── Scan ──────────────────────────────────────────────────────────

    def scan(self) -> list[dict]:
        """Scan all configured paths for git repositories."""
        self._findings = []
        for base_path in self._scan_paths:
            path = Path(base_path)
            if not path.exists():
                continue
            self._scan_directory(path, depth=0)

        info(f"GitDetector: found {len(self._findings)} git repositories")
        return self._findings

    def _scan_directory(self, path: Path, depth: int) -> None:
        """Recursively scan for .git directories."""
        if depth > self._max_depth:
            return

        try:
            # Check if this is a git repo
            git_dir = path / ".git"
            if git_dir.exists() and git_dir.is_dir():
                repo_info = self._inspect_repo(path)
                if repo_info:
                    self._findings.append(repo_info)
                return  # Don't go deeper into git repos

            # Recurse into subdirectories
            for item in path.iterdir():
                if item.is_dir() and not item.name.startswith(".") and item.name not in ("node_modules", "vendor", ".venv", "venv", "__pycache__"):
                    self._scan_directory(item, depth + 1)

        except PermissionError:
            pass
        except OSError:
            pass

    # ── Inspect repo ──────────────────────────────────────────────────

    def _inspect_repo(self, repo_path: Path) -> dict | None:
        """Get branch and recent commit info for a git repo."""
        try:
            # Current branch
            branch = self._run_git(repo_path, "rev-parse", "--abbrev-ref", "HEAD")

            # Recent commits (last 30 days)
            since = " --since='30 days ago'"
            log_cmd = f"log --oneline --since='30 days ago' --format='%h|%s|%ci|%an' -20"
            raw_log = self._run_git(repo_path, *log_cmd.split())

            commits = []
            if raw_log:
                for line in raw_log.strip().split("\n"):
                    parts = line.split("|", 3)
                    if len(parts) == 4:
                        commits.append({
                            "hash": parts[0],
                            "message": parts[1],
                            "date": parts[2],
                            "author": parts[3],
                        })

            # Remote URL
            remote = self._run_git(repo_path, "remote", "get-url", "origin") or ""

            # Determine project name from remote or path
            if remote:
                project = os.path.basename(remote).replace(".git", "")
            else:
                project = repo_path.name

            return {
                "path": str(repo_path),
                "project": project,
                "branch": branch.strip() if branch else "unknown",
                "commits_today": len(commits),
                "recent_commits": commits[:5],
                "remote": remote.strip(),
            }

        except Exception as e:
            warning(f"GitDetector: error inspecting {repo_path}: {e}")
            return None

    def _run_git(self, repo_path: Path, *args: str) -> str | None:
        """Run a git command in the given repo directory."""
        try:
            result = subprocess.run(
                ["git", *args],
                cwd=str(repo_path),
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                return result.stdout
            return None
        except Exception:
            return None

    # ── Report integration ────────────────────────────────────────────

    def get_git_summary(self) -> list[dict]:
        """
        Return a summary of git activity for the daily report.
        Only repos with commits today are included.
        """
        if not self._findings:
            self.scan()

        # Filter repos with activity today
        from datetime import date
        today = date.today().isoformat()
        active = []

        for repo in self._findings:
            today_commits = [
                c for c in repo.get("recent_commits", [])
                if c["date"].startswith(today)
            ]
            if today_commits:
                active.append({
                    "project": repo["project"],
                    "branch": repo["branch"],
                    "commits": today_commits,
                })

        return active
