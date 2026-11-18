"""
Pet Memory — stores things the user asks the pet to remember.
"""

from db.database import get_connection


def remember(content: str, category: str = "general") -> int:
    """Save something to memory. Returns the memory ID."""
    conn = get_connection()
    cursor = conn.execute(
        "INSERT INTO pet_memory (content, category) VALUES (?, ?)",
        (content.strip(), category),
    )
    conn.commit()
    mid = cursor.lastrowid
    conn.close()
    return mid


def forget(memory_id: int) -> bool:
    """Mark a memory as inactive (soft delete)."""
    conn = get_connection()
    conn.execute("UPDATE pet_memory SET active = 0 WHERE id = ?", (memory_id,))
    conn.commit()
    conn.close()
    return True


def get_memories(category: str | None = None, limit: int = 50) -> list[dict]:
    """Get active memories, optionally filtered by category."""
    conn = get_connection()
    if category:
        rows = conn.execute(
            "SELECT * FROM pet_memory WHERE active = 1 AND category = ? ORDER BY created_at DESC LIMIT ?",
            (category, limit),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM pet_memory WHERE active = 1 ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def search_memories(query: str, limit: int = 10) -> list[dict]:
    """Search memories by content."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM pet_memory WHERE active = 1 AND content LIKE ? ORDER BY created_at DESC LIMIT ?",
        (f"%{query}%", limit),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_memory_summary(limit: int = 10) -> str:
    """Get a text summary of recent memories for AI context."""
    memories = get_memories(limit=limit)
    if not memories:
        return ""
    lines = [f"- {m['content']}" for m in memories]
    return "Cosas que recuerdo:\n" + "\n".join(lines)
