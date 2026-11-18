"""
Config Store — persistent key-value config in SQLite.
Stores tokens, assistant name, preferences, etc.
"""

from db.database import get_connection


def get_config(key: str, default: str = "") -> str:
    """Get a config value by key."""
    conn = get_connection()
    row = conn.execute("SELECT value FROM config WHERE key = ?", (key,)).fetchone()
    conn.close()
    return row["value"] if row else default


def set_config(key: str, value: str) -> None:
    """Set a config value (upsert)."""
    conn = get_connection()
    conn.execute(
        "INSERT INTO config (key, value, updated_at) VALUES (?, ?, datetime('now')) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = datetime('now')",
        (key, value),
    )
    conn.commit()
    conn.close()


def delete_config(key: str) -> None:
    """Delete a config key."""
    conn = get_connection()
    conn.execute("DELETE FROM config WHERE key = ?", (key,))
    conn.commit()
    conn.close()


def get_all_config() -> dict:
    """Get all config as a dict."""
    conn = get_connection()
    rows = conn.execute("SELECT key, value FROM config").fetchall()
    conn.close()
    return {r["key"]: r["value"] for r in rows}


# ── Convenience helpers ───────────────────────────────────────

def get_assistant_name() -> str:
    return get_config("assistant_name", "Pet")

def set_assistant_name(name: str) -> None:
    set_config("assistant_name", name)

def get_clickup_token() -> str:
    return get_config("clickup_token", "")

def set_clickup_token(token: str) -> None:
    set_config("clickup_token", token)

def get_deepseek_token() -> str:
    return get_config("deepseek_token", "")

def set_deepseek_token(token: str) -> None:
    set_config("deepseek_token", token)

def get_ai_mode() -> str:
    return get_config("ai_mode", "local")

def set_ai_mode(mode: str) -> None:
    set_config("ai_mode", mode)
