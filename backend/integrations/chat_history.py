"""
Chat History — persistent chat history in SQLite.
Each message is stored per session.
"""

from datetime import datetime, timezone, date
from db.database import get_connection
from services.logger import info


def init_chat_tables() -> None:
    conn = get_connection()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS chat_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('user','assistant','system')),
            content TEXT NOT NULL,
            timestamp TEXT NOT NULL DEFAULT (datetime('now')),
            date TEXT NOT NULL DEFAULT (date('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_ch_session ON chat_history(session_id);
        CREATE INDEX IF NOT EXISTS idx_ch_date ON chat_history(date);
    """)
    conn.commit()
    conn.close()
    info("Chat history tables ready")


def save_message(session_id: str, role: str, content: str) -> int:
    conn = get_connection()
    now = datetime.now(timezone.utc).isoformat()
    today = date.today().isoformat()
    cursor = conn.execute(
        "INSERT INTO chat_history (session_id, role, content, timestamp, date) VALUES (?, ?, ?, ?, ?)",
        (session_id, role, content, now, today),
    )
    conn.commit()
    row_id = cursor.lastrowid
    conn.close()
    return row_id


def get_history(session_id: str, limit: int = 50) -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM chat_history WHERE session_id = ? ORDER BY id DESC LIMIT ?",
        (session_id, limit),
    ).fetchall()
    conn.close()
    return [dict(r) for r in reversed(rows)]  # chronological


def get_today_sessions() -> list[str]:
    conn = get_connection()
    today = date.today().isoformat()
    rows = conn.execute(
        "SELECT DISTINCT session_id FROM chat_history WHERE date = ? ORDER BY id DESC",
        (today,),
    ).fetchall()
    conn.close()
    return [r["session_id"] for r in rows]


def clear_history(session_id: str | None = None) -> int:
    conn = get_connection()
    if session_id:
        cursor = conn.execute("DELETE FROM chat_history WHERE session_id = ?", (session_id,))
    else:
        cursor = conn.execute("DELETE FROM chat_history")
    conn.commit()
    deleted = cursor.rowcount
    conn.close()
    return deleted
