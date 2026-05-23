"""
Database — automatic SQLite setup and connection management.
"""

import sqlite3
import os
from services.logger import info

DB_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
DB_PATH = os.path.join(DB_DIR, "work_assistant.db")


def get_connection() -> sqlite3.Connection:
    """Return a connection to the local SQLite database."""
    os.makedirs(DB_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db() -> None:
    """Create tables if they don't exist."""
    conn = get_connection()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS activities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            activity_type TEXT NOT NULL,
            window_name TEXT NOT NULL,
            duration REAL NOT NULL DEFAULT 0.0,
            session_id TEXT NOT NULL
        )
        """
    )
    conn.commit()
    conn.close()
    info(f"Database initialized at {DB_PATH}")
