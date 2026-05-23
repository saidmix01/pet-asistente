"""
Activity Tracker — simulates user activity by emitting events every 2-5 seconds.
"""

import random
import time
import threading
from datetime import datetime, timezone

from core.event_bus import EventBus
from services.logger import info


ACTIVITY_TYPES = ["coding", "browsing", "reading", "idle"]
WINDOW_NAMES = [
    "Visual Studio Code - main.py",
    "Chrome - Work Assistant Docs",
    "Firefox - Stack Overflow",
    "Terminal - bash session",
    "Slack - team channel",
    "Notion - project notes",
    "Spotify - focus playlist",
]


class ActivityTracker:
    """Simulates user activity and emits events to the EventBus."""

    def __init__(self, event_bus: EventBus) -> None:
        self._bus = event_bus
        self._session_id = f"session_{int(time.time())}"
        self._session_time: float = 0.0
        self._current_type: str = "idle"
        self._running = False
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        info(f"ActivityTracker started (session_id={self._session_id})")

    def stop(self) -> None:
        self._running = False
        info("ActivityTracker stopped")

    def _loop(self) -> None:
        while self._running:
            delay = random.uniform(2.0, 5.0)
            time.sleep(delay)

            self._session_time += delay

            new_type = random.choice(ACTIVITY_TYPES)
            window = random.choice(WINDOW_NAMES)
            now = datetime.now(timezone.utc).isoformat()

            payload = {
                "timestamp": now,
                "activity_type": new_type,
                "previous_type": self._current_type,
                "window_name": window,
                "session_time": round(self._session_time, 2),
                "session_id": self._session_id,
                "duration": round(delay, 2),
            }

            if new_type != self._current_type:
                self._current_type = new_type
                self._bus.emit("activity.switch", payload)

            if new_type == "idle":
                self._bus.emit("activity.idle", payload)
            else:
                self._bus.emit("activity.update", payload)
