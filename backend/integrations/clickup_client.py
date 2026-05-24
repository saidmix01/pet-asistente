"""
ClickUp API client — raw HTTP wrapper for ClickUp API v2.
"""

import json
import os
import ssl
import urllib.parse
import urllib.request
import urllib.error
from typing import Any


# macOS fix: create an SSL context that uses certifi when available
# This avoids CERTIFICATE_VERIFY_FAILED on systems with broken cert bundles
def _ssl_context() -> ssl.SSLContext:
    ctx = ssl.create_default_context()
    try:
        import certifi
        ctx.load_verify_locations(certifi.where())
    except ImportError:
        pass
    return ctx

from services.logger import info, error, warning

BASE_URL = "https://api.clickup.com/api/v2"


class ClickUpClient:
    """Low-level HTTP client for ClickUp REST API."""

    def __init__(self, api_token: str) -> None:
        self._token = api_token

    # ── Auth header helper ────────────────────────────────────────────

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": self._token,
            "Content-Type": "application/json",
        }

    def _request(self, method: str, path: str, data: dict | None = None, timeout: int = 15) -> Any:
        url = f"{BASE_URL}{path}"
        body = json.dumps(data).encode() if data else None
        req = urllib.request.Request(url, data=body, headers=self._headers(), method=method)
        try:
            with urllib.request.urlopen(req, timeout=timeout, context=_ssl_context()) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            body = e.read().decode()
            error(f"ClickUp API {e.code} on {method} {path}: {body[:200]}")
            raise

    # ── Workspaces / Teams ────────────────────────────────────────────

    def get_teams(self) -> list[dict]:
        """Return all workspaces (teams) the user belongs to."""
        data = self._request("GET", "/team")
        return data.get("teams", [])

    # ── Spaces ────────────────────────────────────────────────────────

    def get_spaces(self, team_id: str) -> list[dict]:
        data = self._request("GET", f"/team/{team_id}/space")
        return data.get("spaces", [])

    # ── Folders ───────────────────────────────────────────────────────

    def get_folders(self, space_id: str) -> list[dict]:
        data = self._request("GET", f"/space/{space_id}/folder")
        return data.get("folders", [])

    # ── Lists ─────────────────────────────────────────────────────────

    def get_lists(self, folder_id: str) -> list[dict]:
        data = self._request("GET", f"/folder/{folder_id}/list")
        return data.get("lists", [])

    def get_folderless_lists(self, space_id: str) -> list[dict]:
        """Lists that are directly in a space (not inside a folder)."""
        data = self._request("GET", f"/space/{space_id}/list")
        return data.get("lists", [])

    # ── Tasks ─────────────────────────────────────────────────────────

    def get_tasks(
        self,
        list_id: str,
        page: int = 0,
        order_by: str = "updated",
        reverse: bool = True,
        statuses: list[str] | None = None,
        assignees: list[str] | None = None,
        date_created_gt: int | None = None,
        date_updated_gt: int | None = None,
        include_closed: bool = True,
        subtasks: bool = False,
        max_pages: int = 5,
    ) -> list[dict]:
        """Fetch tasks with pagination (up to max_pages)."""
        all_tasks: list[dict] = []
        for p in range(max_pages):
            params = [
                f"page={p}",
                f"order_by={order_by}",
                f"reverse={'true' if reverse else 'false'}",
                f"include_closed={'true' if include_closed else 'false'}",
                f"subtasks={'true' if subtasks else 'false'}",
            ]
            if statuses:
                for s in statuses:
                    params.append(f"statuses[]={urllib.parse.quote(s)}")
            if assignees:
                for a in assignees:
                    params.append(f"assignees[]={a}")
            if date_created_gt:
                params.append(f"date_created_gt={date_created_gt}")
            if date_updated_gt:
                params.append(f"date_updated_gt={date_updated_gt}")

            qs = "&".join(params)
            data = self._request("GET", f"/list/{list_id}/task?{qs}", timeout=30)
            tasks = data.get("tasks", [])
            all_tasks.extend(tasks)
            if len(tasks) < 100:
                break  # Last page
        return all_tasks

    def get_task(self, task_id: str) -> dict:
        return self._request("GET", f"/task/{task_id}")

    # ── Users ───────────────────────────────────────────────────────────

    def get_current_user(self) -> dict:
        """Return info about the authenticated user."""
        data = self._request("GET", "/user")
        # Response is nested: {"user": {...}}
        return data.get("user", data)

    def get_team_users(self, team_id: str) -> list[dict]:
        """Return members of a team/workspace."""
        data = self._request("GET", f"/team/{team_id}/user")
        return data.get("members", [])

    # ── Team-level Tasks (filtered by assignee) ────────────────────────

    def get_my_tasks(
        self,
        team_id: str,
        assignee_id: str,
        page: int = 0,
        include_closed: bool = True,
        subtasks: bool = True,
        date_updated_gt: int | None = None,
        max_pages: int = 5,
    ) -> list[dict]:
        """
        Fetch ALL tasks assigned to a specific user across the entire team.
        Much more efficient than iterating through every list.
        """
        all_tasks: list[dict] = []
        for p in range(max_pages):
            params = [
                f"page={p}",
                f"assignees[]={assignee_id}",
                f"include_closed={'true' if include_closed else 'false'}",
                f"subtasks={'true' if subtasks else 'false'}",
            ]
            if date_updated_gt:
                params.append(f"date_updated_gt={date_updated_gt}")
            qs = "&".join(params)
            data = self._request("GET", f"/team/{team_id}/task?{qs}", timeout=30)
            tasks = data.get("tasks", [])
            all_tasks.extend(tasks)
            if len(tasks) < 100:
                break
        return all_tasks

    # ── Time Tracking ─────────────────────────────────────────────────

    def get_task_comments(self, task_id: str) -> list[dict]:
        """Get comments for a specific task."""
        return self._request("GET", f"/task/{task_id}/comment") or []

    def get_time_entries(
        self,
        team_id: str,
        start_date: int,
        end_date: int,
        assignee: str | None = None,
    ) -> list[dict]:
        params = [
            f"start_date={start_date}",
            f"end_date={end_date}",
        ]
        if assignee:
            params.append(f"assignee={assignee}")
        qs = "&".join(params)
        data = self._request("GET", f"/team/{team_id}/time_entries?{qs}")
        return data.get("data", [])
