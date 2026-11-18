"""
Pomodoro — focus timer with configurable sessions.
Tracks focus sessions in SQLite.
"""

import time
from datetime import datetime, timezone, date
from typing import Any
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from db.database import get_connection
from services.logger import info

router = APIRouter(prefix="/pomodoro", tags=["pomodoro"])

# ── In-memory state ──────────────────────────────────────────
_pomodoro_state = {
    "active": False,
    "phase": "idle",           # idle, focus, break, long_break
    "elapsed": 0.0,
    "duration": 25 * 60,       # seconds
    "started_at": None,
    "paused": False,
    "paused_elapsed": 0.0,
    "session_count": 0,        # completed focus sessions today
}


def init_pomodoro_tables() -> None:
    conn = get_connection()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS pomodoro_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            phase TEXT NOT NULL,
            duration_seconds REAL NOT NULL,
            started_at TEXT NOT NULL,
            completed_at TEXT,
            status TEXT DEFAULT 'in_progress'
        );
    """)
    conn.commit()
    conn.close()
    info("Pomodoro tables ready")


# ── Routes ────────────────────────────────────────────────────

@router.get("/status")
async def get_status():
    """Get current pomodoro state."""
    s = _pomodoro_state
    now = time.time()
    elapsed = s["elapsed"]
    if s["active"] and not s["paused"] and s["started_at"]:
        elapsed = now - s["started_at"]

    remaining = max(0, s["duration"] - elapsed)

    return {
        "active": s["active"],
        "phase": s["phase"],
        "elapsed": round(elapsed, 1),
        "duration": s["duration"],
        "remaining": round(remaining, 1),
        "paused": s["paused"],
        "session_count": s["session_count"],
        "progress_pct": round(min(elapsed / s["duration"] * 100, 100), 1) if s["duration"] > 0 else 0,
    }


class PomodoroStartRequest(BaseModel):
    duration_minutes: int = 25  # default focus
    phase: str = "focus"        # focus, break, long_break


@router.post("/start")
async def start_pomodoro(req: PomodoroStartRequest):
    """Start a pomodoro session."""
    s = _pomodoro_state
    if s["active"]:
        raise HTTPException(400, "Ya hay un pomodoro activo")

    duration_seconds = req.duration_minutes * 60
    s["active"] = True
    s["phase"] = req.phase
    s["duration"] = duration_seconds
    s["elapsed"] = 0.0
    s["started_at"] = time.time()
    s["paused"] = False
    s["paused_elapsed"] = 0.0

    # Save to DB
    conn = get_connection()
    conn.execute(
        "INSERT INTO pomodoro_sessions (date, phase, duration_seconds, started_at, status) VALUES (?, ?, ?, ?, 'in_progress')",
        (date.today().isoformat(), req.phase, duration_seconds, datetime.now(timezone.utc).isoformat()),
    )
    conn.commit()
    conn.close()

    info(f"Pomodoro started: {req.phase} for {req.duration_minutes}m")
    return {"message": f"Pomodoro iniciado: {req.duration_minutes} min", "phase": req.phase}


@router.post("/stop")
async def stop_pomodoro():
    """Stop the current pomodoro."""
    s = _pomodoro_state
    if not s["active"]:
        raise HTTPException(400, "No hay pomodoro activo")

    s["active"] = False
    s["phase"] = "idle"
    s["started_at"] = None

    # Mark incomplete in DB
    conn = get_connection()
    conn.execute(
        "UPDATE pomodoro_sessions SET status = 'cancelled', completed_at = ? WHERE status = 'in_progress' AND date = ?",
        (datetime.now(timezone.utc).isoformat(), date.today().isoformat()),
    )
    conn.commit()
    conn.close()

    return {"message": "Pomodoro detenido"}


@router.get("/today")
async def today_sessions():
    """Get today's completed pomodoro sessions."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM pomodoro_sessions WHERE date = ? AND status = 'completed' ORDER BY started_at",
        (date.today().isoformat(),),
    ).fetchall()
    conn.close()
    return {"count": len(rows), "sessions": [dict(r) for r in rows]}


# ── Background checker (called from main loop) ──────────────

def check_pomodoro() -> dict | None:
    """
    Check if current pomodoro is finished.
    Returns notification info if completed.
    """
    s = _pomodoro_state
    if not s["active"] or s["paused"] or not s["started_at"]:
        return None

    now = time.time()
    elapsed = now - s["started_at"]

    if elapsed >= s["duration"]:
        # Session complete
        s["active"] = False
        s["phase"] = "idle"
        s["session_count"] += 1

        # Mark complete in DB
        conn = get_connection()
        conn.execute(
            "UPDATE pomodoro_sessions SET status = 'completed', completed_at = ? WHERE status = 'in_progress' AND date = ?",
            (datetime.now(timezone.utc).isoformat(), date.today().isoformat()),
        )
        conn.commit()
        conn.close()

        info(f"Pomodoro completed! Total today: {s['session_count']}")

        # Suggest next: break if focus, focus if break
        return {
            "completed": True,
            "session_count": s["session_count"],
            "suggest": "break" if s["phase"] == "focus" else "focus",
        }

    return None
