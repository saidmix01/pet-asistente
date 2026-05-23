"""
System State — maintains the live, in-memory state of the Work Assistant system.
Updated in real-time by the Processor and exposed via the API.
"""

import time
from datetime import datetime, timezone
from typing import Any

from services.logger import info

# Productivity weights per activity type
PRODUCTIVITY_WEIGHTS = {
    "coding": 1.0,
    "reading": 0.7,
    "browsing": 0.5,
    "idle": 0.0,
}


class SystemState:
    """Live system state maintained in memory."""

    def __init__(self) -> None:
        self._state: dict[str, Any] = {
            "status": "active",
            "current_activity": "idle",
            "current_window": "unknown",
            "session_time": 0.0,
            "productivity_score": 0.0,
            "active_duration": 0.0,
            "idle_duration": 0.0,
            "total_events": 0,
            "last_update": datetime.now(timezone.utc).isoformat(),
        }
        self._session_start: float = time.time()
        self._last_event_time: float = time.time()

    # ── Public API ────────────────────────────────────────────────────

    def get_state(self) -> dict[str, Any]:
        """Return a snapshot of the current live state."""
        self._refresh_timestamps()
        return dict(self._state)

    def handle_event(self, event: str, data: dict) -> None:
        """Process an incoming event and update the internal state."""
        self._state["total_events"] += 1
        self._state["last_update"] = datetime.now(timezone.utc).isoformat()
        self._last_event_time = time.time()

        if event in ("activity.update", "activity.switch"):
            self._apply_activity(data)
        elif event == "activity.idle":
            self._apply_idle(data)

    # ── Internal ──────────────────────────────────────────────────────

    def _apply_activity(self, data: dict) -> None:
        self._state["current_activity"] = data.get("activity_type", "unknown")
        self._state["current_window"] = data.get("window_name", "unknown")
        self._state["session_time"] = data.get("session_time", self._state["session_time"])
        self._recalc_productivity()

        if data.get("activity_type") != "idle":
            self._state["active_duration"] += data.get("duration", 0.0)
        else:
            self._state["idle_duration"] += data.get("duration", 0.0)

    def _apply_idle(self, data: dict) -> None:
        self._state["current_activity"] = "idle"
        self._state["idle_duration"] += data.get("duration", 0.0)
        self._recalc_productivity()

    def _recalc_productivity(self) -> None:
        activity = self._state["current_activity"]
        base_weight = PRODUCTIVITY_WEIGHTS.get(activity, 0.0)

        # Session-length bonus: longer sessions → slight multiplier
        session_minutes = self._state["session_time"] / 60.0
        stamina = min(session_minutes / 120.0, 1.0)  # caps at 2h
        score = base_weight * (0.7 + 0.3 * stamina)

        self._state["productivity_score"] = round(score, 2)

    def _refresh_timestamps(self) -> None:
        """Refresh computed fields before returning state."""
        now = time.time()
        elapsed = now - self._session_start
        self._state["session_time"] = round(elapsed, 2)
        self._state["last_update"] = datetime.now(timezone.utc).isoformat()

        # Auto-idle detection: no event in >10s
        idle_seconds = now - self._last_event_time
        if idle_seconds > 10:
            self._state["current_activity"] = "idle"
            self._state["productivity_score"] = 0.0
