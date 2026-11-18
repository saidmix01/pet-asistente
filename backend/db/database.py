"""
Database — automatic SQLite setup and connection management.
"""

import sqlite3
import os
import sys
from services.logger import info


def get_data_dir() -> str:
    """Get persistent data directory. Uses AppData on Windows and XDG data dir on Linux/macOS when frozen."""
    # If running as PyInstaller bundle, use a persistent location
    if getattr(sys, 'frozen', False):
        if os.name == 'nt':
            base = os.environ.get('APPDATA', os.path.expanduser('~'))
        else:
            base = os.environ.get('XDG_DATA_HOME', os.path.expanduser('~/.local/share'))
        return os.path.join(base, 'pet-asistente', 'data')
    else:
        # Running as script (dev mode)
        return os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")


_get_data_dir = get_data_dir
DB_DIR = get_data_dir()
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
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS activities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            activity_type TEXT NOT NULL,
            window_name TEXT NOT NULL,
            duration REAL NOT NULL DEFAULT 0.0,
            session_id TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS config (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS pet_memory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            content TEXT NOT NULL,
            category TEXT DEFAULT 'general',
            created_at TEXT DEFAULT (datetime('now')),
            active INTEGER DEFAULT 1
        );

        CREATE INDEX IF NOT EXISTS idx_activities_time ON activities(timestamp);
        CREATE INDEX IF NOT EXISTS idx_activities_session ON activities(session_id);
        CREATE INDEX IF NOT EXISTS idx_activities_type ON activities(activity_type);
    """)
    conn.commit()
    conn.close()
    info(f"Database initialized at {DB_PATH}")
