"""
Task Tracker — monitors ClickUp tasks for status changes, new descriptions,
and completed checklists. Automatically logs activity to daily_log.
"""

import time
from datetime import datetime, timezone, timedelta
from typing import Any

from integrations.clickup_client import ClickUpClient
from integrations.clickup_config import load_token
from integrations.clickup_db import upsert_tasks, get_cached_tasks
from integrations.daily_log import add_log_entry
from services.logger import info, warning, error


# Statuses that mean "actively working"
ACTIVE_STATUSES = ["in progress", "in review", "doing"]
# Status that means "completed"
COMPLETED_STATUSES = ["revision", "done", "completed", "closed"]


class TaskTracker:
    """
    Polls ClickUp for the user's tasks, detects status changes,
    and auto-registers daily log entries.
    """

    def __init__(self, poll_interval: int = 60, time_tracker=None) -> None:
        self._client: ClickUpClient | None = None
        self._user_id: str | None = None
        self._team_id: str | None = None
        self._poll_interval = poll_interval
        self._running = False
        self._thread = None
        self._time_tracker = time_tracker

        # Track last known states per task ID
        self._last_states: dict[str, str] = {}
        self._last_descriptions: dict[str, str] = {}
        self._last_checklists: dict[str, list[dict]] = {}

        # Active tasks (currently being worked on)
        self._active_tasks: dict[str, dict] = {}

    # ── Lifecycle ─────────────────────────────────────────────────────

    def start(self) -> None:
        token = load_token()
        if not token:
            warning("TaskTracker: no ClickUp token, skipping")
            return

        self._client = ClickUpClient(token)

        # Get user info
        user = self._client.get_current_user()
        self._user_id = str(user.get("id", ""))

        # Get teams
        teams = self._client.get_teams()
        if teams:
            self._team_id = teams[0]["id"]

        if not self._user_id or not self._team_id:
            error("TaskTracker: could not get user/team info")
            return

        self._running = True
        import threading
        self._thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._thread.start()
        info(f"TaskTracker started (user={self._user_id}, team={self._team_id})")

    def stop(self) -> None:
        self._running = False
        info("TaskTracker stopped")

    # ── Polling loop ──────────────────────────────────────────────────

    def _poll_loop(self) -> None:
        while self._running:
            try:
                self._check_tasks()
            except Exception as e:
                error(f"TaskTracker poll error: {e}")
            time.sleep(self._poll_interval)

    def _check_tasks(self) -> None:
        """Fetch tasks and detect changes."""
        if not self._client or not self._user_id or not self._team_id:
            return

        # Fetch my tasks (recently updated)
        tasks = self._client.get_my_tasks(
            team_id=self._team_id,
            assignee_id=self._user_id,
            date_updated_gt=int(
                (datetime.now(timezone.utc) - timedelta(days=30)).timestamp() * 1000
            ),
            subtasks=True,
            max_pages=3,
        )

        for task in tasks:
            tid = task.get("id", "")
            name = task.get("name", "")
            status_obj = task.get("status", {})
            status = status_obj.get("status", "").lower() if status_obj else ""
            description = task.get("description", "") or ""

            # Detect status changes
            old_status = self._last_states.get(tid)
            self._last_states[tid] = status

            if old_status and old_status != status:
                self._on_status_change(tid, name, old_status, status, task)

            # Detect description changes
            old_desc = self._last_descriptions.get(tid, "")
            if description and description != old_desc:
                self._last_descriptions[tid] = description
                self._on_description_change(tid, name, description, task, status)

            # Detect checklist changes
            checklists = task.get("checklists", [])
            old_cl = self._last_checklists.get(tid, [])
            if checklists and old_cl != checklists:
                self._last_checklists[tid] = checklists
                self._on_checklist_change(tid, name, checklists, task, status)

    # ── Event handlers ────────────────────────────────────────────────

    def _compute_progress(self, task: dict) -> int:
        """
        Compute progress percentage based on:
        - Checklists completed vs total
        - Subtask statuses
        - Default: 50% for active, 100% for completed
        """
        status_obj = task.get("status", {}) or {}
        status = (status_obj.get("status", "") or "").lower()

        if status in COMPLETED_STATUSES:
            return 100

        # Check checklists
        checklists = task.get("checklists", []) or []
        total_items = 0
        done_items = 0
        for cl in checklists:
            items = cl.get("items", []) or []
            for item in items:
                total_items += 1
                if item.get("resolved", False):
                    done_items += 1

        if total_items > 0:
            return int((done_items / total_items) * 100)

        # Check subtasks
        subtasks = task.get("subtasks", []) or []
        if subtasks:
            done = sum(1 for s in subtasks if (s.get("status", {}) or {}).get("status", "").lower() in COMPLETED_STATUSES)
            return int((done / len(subtasks)) * 100)

        # Default
        return 50 if status in ACTIVE_STATUSES else 0

    def _on_status_change(
        self,
        task_id: str,
        task_name: str,
        old_status: str,
        new_status: str,
        task: dict,
    ) -> None:
        info(f"Task status changed: {task_name} ({old_status} → {new_status})")

        today = datetime.now(timezone.utc).date().isoformat()
        project = task.get("project", {}) or {}
        project_name = project.get("name", "") if isinstance(project, dict) else ""
        list_obj = task.get("list", {}) or {}
        list_name = list_obj.get("name", "") if isinstance(list_obj, dict) else ""
        parent = task.get("parent")
        is_subtask = parent is not None

        # If became active (in progress / doing)
        if new_status in ACTIVE_STATUSES and old_status not in ACTIVE_STATUSES:
            # Start time tracking
            if self._time_tracker:
                self._time_tracker.start_task(
                    task_id=task_id,
                    task_name=task_name,
                    project_name=project_name,
                    list_name=list_name,
                )

            notes = f"Started working (status: {new_status})"
            add_log_entry(
                date=today,
                clickup_task_id=task_id,
                project_name=project_name,
                list_name=list_name,
                task_name=task_name,
                progress=50,
                description=notes,
            )
            self._active_tasks[task_id] = {"name": task_name, "started": time.time()}

        # If became completed (revision / done)
        if new_status in COMPLETED_STATUSES:
            # Stop time tracking
            if self._time_tracker:
                self._time_tracker.stop_task()

            # Get total time spent
            time_spent = ""
            if self._time_tracker:
                total_secs = self._time_tracker.get_task_total_time(task_id)
                mins = int(total_secs // 60)
                hrs = mins // 60
                if hrs > 0:
                    time_spent = f"⏱️ {hrs}h {mins % 60}m"
                else:
                    time_spent = f"⏱️ {mins}m"

            # Compute progress from checklists + subtasks
            progress = self._compute_progress(task)

            description_text = task.get("description", "") or ""
            checklist_summary = self._summarize_checklists(task.get("checklists", []) or [])

            notes_parts = []
            if time_spent:
                notes_parts.append(time_spent)
            if description_text:
                notes_parts.append(description_text[:500])
            if checklist_summary:
                notes_parts.append(checklist_summary)
            if not notes_parts:
                notes_parts.append(f"Task marked as {new_status}")

            notes = "\n".join(notes_parts)

            add_log_entry(
                date=today,
                clickup_task_id=task_id,
                project_name=project_name,
                list_name=list_name,
                task_name=task_name,
                progress=progress,
                description=notes,
            )

            if task_id in self._active_tasks:
                del self._active_tasks[task_id]

    def _on_description_change(
        self,
        task_id: str,
        task_name: str,
        description: str,
        task: dict,
        status: str,
    ) -> None:
        # Only log if task is active (in progress)
        if status in ACTIVE_STATUSES or status in COMPLETED_STATUSES:
            info(f"Description updated on task: {task_name}")
            # Description is already captured in status change events,
            # so we don't need to add another log entry here

    def _on_checklist_change(
        self,
        task_id: str,
        task_name: str,
        checklists: list[dict],
        task: dict,
        status: str,
    ) -> None:
        if not checklists:
            return
        info(f"Checklist updated on task: {task_name}")

    # ── Helpers ───────────────────────────────────────────────────────

    def _summarize_checklists(self, checklists: list[dict]) -> str:
        """Get a summary of completed/uncompleted checklist items."""
        if not checklists:
            return ""

        lines = []
        for cl in checklists:
            cl_name = cl.get("name", "Checklist")
            items = cl.get("items", [])
            total = len(items)
            done = sum(1 for i in items if i.get("resolved", False))
            lines.append(f"{cl_name}: {done}/{total}")

            # List completed items
            for i in items:
                if i.get("resolved", False):
                    lines.append(f"  ✅ {i.get('name', '')}")

        return "\n".join(lines)

    # ── Active task info ──────────────────────────────────────────────

    def get_active_tasks(self) -> list[dict]:
        """Return tasks currently being worked on."""
        return [
            {
                "task_id": tid,
                "name": t["name"],
                "elapsed": round(time.time() - t["started"], 2),
            }
            for tid, t in self._active_tasks.items()
        ]

    def get_current_task(self) -> dict | None:
        """Return the most recently activated task, if any."""
        if not self._active_tasks:
            return None
        latest = max(self._active_tasks.items(), key=lambda x: x[1]["started"])
        return {
            "task_id": latest[0],
            "name": latest[1]["name"],
            "elapsed": round(time.time() - latest[1]["started"], 2),
        }
