"""
Activity Service — persistence and query layer for activity data.
"""

from db.database import get_connection
from db.models import ActivityRecord
from services.logger import info


class ActivityService:
    """Handles saving and querying activity records."""

    # ── Save ──────────────────────────────────────────────────────────

    def save_activity(self, record: dict) -> int:
        conn = get_connection()
        cursor = conn.execute(
            """
            INSERT INTO activities (timestamp, activity_type, window_name, duration, session_id)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                record["timestamp"],
                record["activity_type"],
                record["window_name"],
                record["duration"],
                record["session_id"],
            ),
        )
        conn.commit()
        row_id = cursor.lastrowid
        conn.close()
        info(f"Saved activity #{row_id}: {record['activity_type']}")
        return row_id

    # ── Queries ───────────────────────────────────────────────────────

    def get_recent(self, limit: int = 20) -> list[ActivityRecord]:
        conn = get_connection()
        rows = conn.execute(
            "SELECT * FROM activities ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        conn.close()
        return [ActivityRecord(**dict(r)) for r in rows]

    def get_today_summary(self) -> dict:
        conn = get_connection()
        rows = conn.execute(
            """
            SELECT activity_type, COUNT(*) as count, ROUND(SUM(duration), 2) as total_duration
            FROM activities
            WHERE date(timestamp) = date('now')
            GROUP BY activity_type
            ORDER BY count DESC
            """
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]
