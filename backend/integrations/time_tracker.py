"""
Time Tracker — correlates active window/app with ClickUp task to measure
actual time spent on each task.
"""

import time
from datetime import datetime, timezone, date
from typing import Any

from services.logger import info, warning
from db.database import get_connection


def init_time_tracking_tables() -> None:
    conn = get_connection()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS task_time_entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            clickup_task_id TEXT NOT NULL,
            project_name TEXT NOT NULL DEFAULT '',
            list_name TEXT NOT NULL DEFAULT '',
            task_name TEXT NOT NULL DEFAULT '',
            start_time TEXT NOT NULL,
            end_time TEXT,
            duration_seconds REAL DEFAULT 0,
            status TEXT DEFAULT 'in_progress',
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_tte_date ON task_time_entries(date);
        CREATE INDEX IF NOT EXISTS idx_tte_task ON task_time_entries(clickup_task_id);
    """)
    conn.commit()
    conn.close()
    info("Time tracking tables ready")


class TimeTracker:
    """
    Tracks time spent on each ClickUp task.
    Started when a task goes to 'in progress', paused on idle/switch.
    """

    def __init__(self) -> None:
        self._current_entry_id: int | None = None
        self._current_task_id: str | None = None
        self._start_time: float | None = None
        self._last_app: str = ""

    # ── Lifecycle ─────────────────────────────────────────────────────

    def start_task(
        self,
        task_id: str,
        task_name: str,
        project_name: str = "",
        list_name: str = "",
    ) -> int:
        """Start tracking time on a task. Stops previous if any."""
        # Stop previous task
        self.stop_task()

        now = datetime.now(timezone.utc).isoformat()
        conn = get_connection()
        cursor = conn.execute(
            """INSERT INTO task_time_entries
               (date, clickup_task_id, project_name, list_name, task_name, start_time, status)
               VALUES (?, ?, ?, ?, ?, ?, 'in_progress')""",
            (date.today().isoformat(), task_id, project_name, list_name, task_name, now),
        )
        conn.commit()
        self._current_entry_id = cursor.lastrowid
        self._current_task_id = task_id
        self._start_time = time.time()
        conn.close()
        info(f"TimeTracker: started tracking '{task_name}' ({task_id})")
        return self._current_entry_id

    def stop_task(self) -> dict | None:
        """Stop current time tracking entry. Returns duration info."""
        if self._current_entry_id is None or self._start_time is None:
            return None

        duration = round(time.time() - self._start_time, 2)
        now = datetime.now(timezone.utc).isoformat()

        conn = get_connection()
        conn.execute(
            "UPDATE task_time_entries SET end_time = ?, duration_seconds = ?, status = 'completed' WHERE id = ?",
            (now, duration, self._current_entry_id),
        )
        conn.commit()
        conn.close()

        result = {
            "entry_id": self._current_entry_id,
            "task_id": self._current_task_id,
            "duration": duration,
        }
        info(f"TimeTracker: stopped tracking {self._current_task_id}, duration={duration}s")
        self._current_entry_id = None
        self._current_task_id = None
        self._start_time = None
        return result

    def get_current_task_id(self) -> str | None:
        return self._current_task_id

    def is_tracking(self) -> bool:
        return self._current_entry_id is not None

    def get_current_duration(self) -> float:
        """Return elapsed seconds for the current task."""
        if self._start_time is None:
            return 0.0
        return round(time.time() - self._start_time, 2)

    # ── Queries ───────────────────────────────────────────────────────

    def get_today_entries(self) -> list[dict]:
        conn = get_connection()
        rows = conn.execute(
            """SELECT * FROM task_time_entries
               WHERE date = ?
               ORDER BY start_time DESC""",
            (date.today().isoformat(),),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def get_task_total_time(self, task_id: str) -> float:
        """Sum of all time entries for a task today."""
        conn = get_connection()
        row = conn.execute(
            "SELECT COALESCE(SUM(duration_seconds), 0) as total FROM task_time_entries WHERE clickup_task_id = ? AND date = ?",
            (task_id, date.today().isoformat()),
        ).fetchone()
        conn.close()
        return row["total"] if row else 0.0

    def get_project_time_summary(self) -> dict:
        """Return time grouped by project for today."""
        conn = get_connection()
        rows = conn.execute(
            """SELECT project_name, clickup_task_id, task_name,
                      SUM(duration_seconds) as total_seconds,
                      COUNT(*) as sessions
               FROM task_time_entries
               WHERE date = ?
               GROUP BY project_name, clickup_task_id
               ORDER BY total_seconds DESC""",
            (date.today().isoformat(),),
        ).fetchall()
        conn.close()

        projects = {}
        for r in rows:
            d = dict(r)
            proj = d["project_name"] or "Sin proyecto"
            if proj not in projects:
                projects[proj] = 0.0
            projects[proj] += d["total_seconds"]

        return projects
