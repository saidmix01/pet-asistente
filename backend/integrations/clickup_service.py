"""
ClickUp Service — high-level operations: sync, query, and report generation.
"""

from datetime import datetime, timezone
from typing import Any

from integrations.clickup_client import ClickUpClient
from integrations.clickup_config import load_token
from integrations.clickup_db import (
    init_clickup_tables,
    clear_cache,
    upsert_teams,
    upsert_spaces,
    upsert_folders,
    upsert_lists,
    upsert_tasks,
    get_cached_tasks,
    get_cached_structure,
)
from services.logger import info, error


class ClickUpService:
    """High-level service for ClickUp integration."""

    def __init__(self) -> None:
        self._client: ClickUpClient | None = None
        self._user_id: str | None = None
        self._username: str | None = None

    # ── Connection ────────────────────────────────────────────────────

    def is_configured(self) -> bool:
        """Return True if an API token is stored."""
        token = load_token()
        return bool(token and token.strip())

    def is_connected(self) -> bool:
        """Check if the client is valid and connected to ClickUp API."""
        if self._client is not None and self._user_id:
            return True
        token = load_token()
        if not token:
            return False
        # Try lightweight verification
        try:
            client = ClickUpClient(token)
            user = client.get_current_user()
            self._client = client
            self._user_id = str(user.get("id", ""))
            self._username = user.get("username", "") or user.get("email", "")
            return bool(self._user_id)
        except Exception as e:
            error(f"ClickUp verify failed: {e}")
            return False

    def connect(self, token: str) -> dict:
        """Test connection and fetch user/team info."""
        clean_token = (token or "").strip().replace("Bearer ", "").strip().strip('"').strip("'")
        if not clean_token:
            raise ValueError("El token de ClickUp no puede estar vacío")

        client = ClickUpClient(clean_token)

        # 1. Verify user
        user = client.get_current_user()
        user_id = str(user.get("id", ""))
        username = user.get("username", "") or user.get("email", "")
        if not user_id:
            raise ValueError("No se pudo obtener el usuario asociado al token")

        # 2. Verify teams / workspaces
        teams = client.get_teams()
        if not teams:
            raise ValueError("No se encontraron Workspaces (espacios de trabajo) para este token")

        # Connection verified! Save credentials & state
        from integrations.clickup_config import save_token
        save_token(clean_token)
        self._client = client
        self._user_id = user_id
        self._username = username

        team_names = [t.get("name", "") for t in teams]
        info(f"Connected to ClickUp as {username} (user_id={user_id}). Workspaces: {', '.join(team_names)}")

        return {
            "user_id": self._user_id,
            "user": self._username,
            "teams": [{"id": str(t["id"]), "name": t.get("name", "")} for t in teams],
        }

    def disconnect(self) -> None:
        """Remove stored token and reset client cache."""
        from integrations.clickup_config import delete_token
        delete_token()
        self._client = None
        self._user_id = None
        self._username = None
        try:
            clear_cache()
        except Exception:
            pass
        info("ClickUp disconnected")

    # ── Client lazy loader ────────────────────────────────────────────

    def _ensure_client(self) -> ClickUpClient:
        if self._client is not None:
            return self._client
        token = load_token()
        if not token:
            raise RuntimeError("ClickUp no está configurado. Introduce tu API token primero.")
        self._client = ClickUpClient(token)
        return self._client

    # ── Sync ──────────────────────────────────────────────────────────

    def sync_all(self, days_back: int = 30) -> dict:
        """
        Smart sync:
        - Structure: teams → spaces → folders → lists (one pass)
        - Tasks: fetches user tasks + team open tasks
        """
        import time
        client = self._ensure_client()
        init_clickup_tables()
        clear_cache()

        # Get current user ID if not already stored
        if not self._user_id:
            try:
                user = client.get_current_user()
                self._user_id = str(user.get("id", ""))
                self._username = user.get("username", "") or user.get("email", "")
            except Exception as e:
                error(f"ClickUp could not get user profile: {e}")

        teams = client.get_teams()
        upsert_teams(teams)

        start = time.time()
        total_tasks = 0
        total_lists = 0

        for team in teams:
            tid = str(team["id"])

            # ── Structure (spaces → folders → lists) ────────────────
            spaces = client.get_spaces(tid)
            upsert_spaces(spaces, tid)

            for space in spaces:
                sid = str(space["id"])
                folders = client.get_folders(sid)
                upsert_folders(folders, sid)
                for folder in folders:
                    folder_lists = client.get_lists(str(folder["id"]))
                    upsert_lists(folder_lists, str(folder["id"]), sid)
                    total_lists += len(folder_lists)

                # Folderless lists
                folderless = client.get_folderless_lists(sid)
                upsert_lists(folderless, None, sid)
                total_lists += len(folderless)

            # ── Tasks ──────────────────────────────────────────────
            fetched_tasks: list[dict] = []
            seen_ids: set[str] = set()

            # 1. Fetch tasks assigned to the user
            if self._user_id:
                try:
                    my_tasks = client.get_team_tasks(
                        team_id=tid,
                        assignee_id=self._user_id,
                        include_closed=True,
                        subtasks=True,
                        max_pages=5,
                    )
                    for t in my_tasks:
                        tid_str = str(t.get("id", ""))
                        if tid_str and tid_str not in seen_ids:
                            seen_ids.add(tid_str)
                            fetched_tasks.append(t)
                    if my_tasks:
                        info(f"  Synced {len(my_tasks)} tasks assigned to {self._username or self._user_id}")
                except Exception as e:
                    error(f"Error fetching user tasks: {e}")

            # 2. If no tasks assigned or few tasks, also fetch open workspace tasks
            if len(fetched_tasks) < 50:
                try:
                    team_tasks = client.get_team_tasks(
                        team_id=tid,
                        assignee_id=None,
                        include_closed=False,
                        subtasks=True,
                        max_pages=3,
                    )
                    added = 0
                    for t in team_tasks:
                        tid_str = str(t.get("id", ""))
                        if tid_str and tid_str not in seen_ids:
                            seen_ids.add(tid_str)
                            fetched_tasks.append(t)
                            added += 1
                    if added > 0:
                        info(f"  Synced {added} workspace tasks without direct assignee filter")
                except Exception as e:
                    error(f"Error fetching team tasks: {e}")

            if fetched_tasks:
                upsert_tasks(fetched_tasks)
                total_tasks += len(fetched_tasks)

        elapsed = round(time.time() - start, 2)
        info(f"Sync complete: {total_lists} lists, {total_tasks} tasks in {elapsed}s")
        return {
            "teams": len(teams),
            "lists": total_lists,
            "tasks_synced": total_tasks,
            "user": self._username or self._user_id,
            "elapsed": elapsed,
        }

    # ── Queries ───────────────────────────────────────────────────────

    def get_structure(self) -> dict:
        return get_cached_structure()

    def get_tasks(
        self,
        list_id: str | None = None,
        status: str | None = None,
        limit: int = 50,
    ) -> list[dict]:
        return get_cached_tasks(list_id=list_id, status=status, limit=limit)

    def get_today_tasks(self) -> list[dict]:
        """Return tasks updated in the last 24 hours."""
        return get_cached_tasks(limit=200)

    # ── Report ────────────────────────────────────────────────────────

    def generate_daily_report(self) -> dict:
        """Generate end-of-day report crossing activity data with ClickUp tasks."""
        from services.activity_service import ActivityService
        from db.database import get_connection

        activity_svc = ActivityService()
        summary = activity_svc.get_today_summary()
        recent_activities = activity_svc.get_recent(limit=200)

        # Get today's cached tasks
        today_tasks = get_cached_tasks(limit=100)

        # Group activities by type for time breakdown
        time_breakdown = {item["activity_type"]: {
            "count": item["count"],
            "total_duration": item["total_duration"],
        } for item in summary}

        # Identify projects from tasks
        projects = {}
        for task in today_tasks:
            pname = task.get("project_name", "Sin proyecto") or "Sin proyecto"
            if pname not in projects:
                projects[pname] = {"tasks": [], "total": 0}
            projects[pname]["tasks"].append({
                "id": task["id"],
                "name": task["name"],
                "status": task["status"],
            })
            projects[pname]["total"] += 1

        return {
            "date": datetime.now(timezone.utc).date().isoformat(),
            "time_breakdown": time_breakdown,
            "total_activities": len(recent_activities),
            "projects": projects,
            "tasks_in_clickup": len(today_tasks),
        }
