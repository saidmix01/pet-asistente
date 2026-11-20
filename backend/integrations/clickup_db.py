"""
ClickUp database layer — table setup and CRUD for cached ClickUp data.
"""

from db.database import get_connection
from services.logger import info


def init_clickup_tables() -> None:
    """Create ClickUp cache tables if they don't exist."""
    conn = get_connection()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS clickup_teams (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            synced_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS clickup_spaces (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            team_id TEXT NOT NULL,
            synced_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS clickup_folders (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            space_id TEXT NOT NULL,
            synced_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS clickup_lists (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            folder_id TEXT,
            space_id TEXT NOT NULL,
            synced_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS clickup_tasks (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT '',
            description TEXT DEFAULT '',
            assignees TEXT DEFAULT '[]',
            tags TEXT DEFAULT '[]',
            priority INTEGER,
            due_date TEXT,
            list_id TEXT NOT NULL,
            project_name TEXT DEFAULT '',
            url TEXT DEFAULT '',
            updated_at TEXT DEFAULT '',
            synced_at TEXT DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_ct_list ON clickup_tasks(list_id);
        CREATE INDEX IF NOT EXISTS idx_ct_status ON clickup_tasks(status);
    """)
    conn.commit()
    conn.close()
    info("ClickUp cache tables ready")


# ── Cache CRUD ────────────────────────────────────────────────────────


def clear_cache() -> None:
    conn = get_connection()
    for table in ["clickup_teams", "clickup_spaces", "clickup_folders", "clickup_lists", "clickup_tasks"]:
        conn.execute(f"DELETE FROM {table}")
    conn.commit()
    conn.close()
    info("ClickUp cache cleared")


def upsert_teams(teams: list[dict]) -> None:
    conn = get_connection()
    for t in teams:
        conn.execute(
            "INSERT OR REPLACE INTO clickup_teams (id, name) VALUES (?, ?)",
            (t["id"], t["name"]),
        )
    conn.commit()
    conn.close()


def upsert_spaces(spaces: list[dict], team_id: str) -> None:
    conn = get_connection()
    for s in spaces:
        conn.execute(
            "INSERT OR REPLACE INTO clickup_spaces (id, name, team_id) VALUES (?, ?, ?)",
            (s["id"], s["name"], team_id),
        )
    conn.commit()
    conn.close()


def upsert_folders(folders: list[dict], space_id: str) -> None:
    conn = get_connection()
    for f in folders:
        conn.execute(
            "INSERT OR REPLACE INTO clickup_folders (id, name, space_id) VALUES (?, ?, ?)",
            (f["id"], f["name"], space_id),
        )
    conn.commit()
    conn.close()


def upsert_lists(lists: list[dict], folder_id: str | None, space_id: str) -> None:
    conn = get_connection()
    for lst in lists:
        conn.execute(
            "INSERT OR REPLACE INTO clickup_lists (id, name, folder_id, space_id) VALUES (?, ?, ?, ?)",
            (lst["id"], lst["name"], folder_id, space_id),
        )
    conn.commit()
    conn.close()


def upsert_tasks(tasks: list[dict]) -> None:
    conn = get_connection()
    import json
    for t in tasks:
        try:
            task_id = str(t.get("id", "")).strip()
            if not task_id:
                continue

            name = str(t.get("name") or "Sin nombre")

            # Status can be dict {"status": "to do"} or string
            st = t.get("status")
            status_val = st.get("status", "") if isinstance(st, dict) else str(st or "")

            # Assignees
            raw_assignees = t.get("assignees", [])
            assignee_names = []
            if isinstance(raw_assignees, list):
                for a in raw_assignees:
                    if isinstance(a, dict):
                        assignee_names.append(a.get("username") or a.get("email") or str(a.get("id", "")))
                    elif isinstance(a, str):
                        assignee_names.append(a)
            assignees = json.dumps(assignee_names)

            # Tags
            raw_tags = t.get("tags", [])
            tag_names = []
            if isinstance(raw_tags, list):
                for tag in raw_tags:
                    if isinstance(tag, dict):
                        tag_names.append(tag.get("name", ""))
                    elif isinstance(tag, str):
                        tag_names.append(tag)
            tags = json.dumps(tag_names)

            # Priority
            priority = t.get("priority")
            priority_val = None
            if isinstance(priority, dict):
                priority_val = priority.get("priority") or priority.get("id")
            elif priority is not None:
                priority_val = priority

            due = t.get("due_date")
            project = t.get("project")
            project_name = project.get("name", "") if isinstance(project, dict) else ""

            list_obj = t.get("list")
            list_id = str(list_obj.get("id", "") if isinstance(list_obj, dict) else (list_obj or ""))
            url = str(t.get("url") or f"https://app.clickup.com/t/{task_id}")
            updated_at = str(t.get("date_updated") or "")

            conn.execute(
                """INSERT OR REPLACE INTO clickup_tasks
                   (id, name, status, description, assignees, tags, priority, due_date, list_id, project_name, url, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    task_id,
                    name,
                    status_val,
                    str(t.get("description") or ""),
                    assignees,
                    tags,
                    priority_val,
                    due,
                    list_id,
                    project_name,
                    url,
                    updated_at,
                ),
            )
        except Exception as e:
            error(f"Error upserting ClickUp task {t.get('id')}: {e}")
    conn.commit()
    conn.close()


# ── Queries ────────────────────────────────────────────────────────────


def get_cached_tasks(
    list_id: str | None = None,
    status: str | None = None,
    limit: int = 50,
) -> list[dict]:
    conn = get_connection()
    sql = "SELECT * FROM clickup_tasks WHERE 1=1"
    params = []
    if list_id:
        sql += " AND list_id = ?"
        params.append(list_id)
    if status:
        sql += " AND status = ?"
        params.append(status)
    sql += " ORDER BY updated_at DESC LIMIT ?"
    params.append(limit)
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_cached_structure() -> dict:
    """Return full workspace hierarchy: teams → spaces → folders → lists."""
    conn = get_connection()
    teams = [dict(r) for r in conn.execute("SELECT * FROM clickup_teams").fetchall()]
    for t in teams:
        t["spaces"] = [dict(r) for r in conn.execute(
            "SELECT * FROM clickup_spaces WHERE team_id = ?", (t["id"],)
        ).fetchall()]
        for s in t["spaces"]:
            s["folders"] = [dict(r) for r in conn.execute(
                "SELECT * FROM clickup_folders WHERE space_id = ?", (s["id"],)
            ).fetchall()]
            for f in s["folders"]:
                f["lists"] = [dict(r) for r in conn.execute(
                    "SELECT * FROM clickup_lists WHERE folder_id = ?", (f["id"],)
                ).fetchall()]
            s["folderless_lists"] = [dict(r) for r in conn.execute(
                "SELECT * FROM clickup_lists WHERE folder_id IS NULL AND space_id = ?", (s["id"],)
            ).fetchall()]
    conn.close()
    return {"teams": teams}
