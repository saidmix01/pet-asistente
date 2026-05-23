"""
Daily Log — database layer for daily work log entries linked to ClickUp tasks.
"""

from db.database import get_connection
from services.logger import info


def init_daily_log_tables() -> None:
    conn = get_connection()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS daily_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            clickup_task_id TEXT NOT NULL DEFAULT '',
            project_name TEXT NOT NULL,
            list_name TEXT NOT NULL,
            task_name TEXT NOT NULL,
            progress INTEGER NOT NULL DEFAULT 0,
            description TEXT NOT NULL DEFAULT '',
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS daily_log_subtasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            log_id INTEGER NOT NULL,
            subtask_name TEXT NOT NULL,
            progress INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY (log_id) REFERENCES daily_logs(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_dl_date ON daily_logs(date);
    """)
    conn.commit()
    conn.close()
    info("Daily log tables ready")


def add_log_entry(
    date: str,
    clickup_task_id: str,
    project_name: str,
    list_name: str,
    task_name: str,
    progress: int = 0,
    description: str = "",
    subtasks: list[dict] | None = None,
) -> int:
    conn = get_connection()
    cursor = conn.execute(
        """INSERT INTO daily_logs (date, clickup_task_id, project_name, list_name, task_name, progress, description)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (date, clickup_task_id, project_name, list_name, task_name, progress, description),
    )
    log_id = cursor.lastrowid

    if subtasks:
        for st in subtasks:
            conn.execute(
                "INSERT INTO daily_log_subtasks (log_id, subtask_name, progress) VALUES (?, ?, ?)",
                (log_id, st.get("name", ""), st.get("progress", 0)),
            )

    conn.commit()
    conn.close()
    return log_id


def get_logs_by_date(date: str) -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM daily_logs WHERE date = ? ORDER BY id", (date,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_subtasks_by_log_id(log_id: int) -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM daily_log_subtasks WHERE log_id = ?", (log_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_recent_logs(limit: int = 20) -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM daily_logs ORDER BY id DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    logs = [dict(r) for r in rows]
    for log in logs:
        log["subtasks"] = get_subtasks_by_log_id(log["id"])
    return logs


def delete_log_entry(entry_id: int) -> bool:
    conn = get_connection()
    conn.execute("DELETE FROM daily_log_subtasks WHERE log_id = ?", (entry_id,))
    cursor = conn.execute("DELETE FROM daily_logs WHERE id = ?", (entry_id,))
    conn.commit()
    deleted = cursor.rowcount > 0
    conn.close()
    return deleted


def generate_report(date: str) -> str:
    """
    Generate formatted daily report linked to ClickUp:

    - (Project) Task Name: progress%
      * Subtask: progress%
      Description lines
    """
    logs = get_logs_by_date(date)

    if not logs:
        return f"No hay registros para {date}"

    lines: list[str] = []
    lines.append(f"📋 Reporte diario — {date}")
    lines.append("")

    for entry in logs:
        task_line = f"- ({entry['project_name']}) {entry['task_name']}: {entry['progress']}%"
        lines.append(task_line)

        # Subtasks
        subtasks = get_subtasks_by_log_id(entry["id"])
        for st in subtasks:
            lines.append(f"  * {st['subtask_name']}: {st['progress']}%")

        # Description
        if entry["description"]:
            for note in entry["description"].split("\n"):
                note = note.strip()
                if note:
                    lines.append(f"  {note}")

        lines.append("")  # blank line separator

    return "\n".join(lines).strip()
