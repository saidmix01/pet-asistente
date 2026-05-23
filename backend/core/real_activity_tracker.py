"""
Real Activity Tracker — monitors actual user activity on macOS.
Detects frontmost app, window title, and system idle time.

Fallbacks to simulated activity if real detection fails.
"""

import subprocess
import threading
import time
import random
from datetime import datetime, timezone

from core.event_bus import EventBus
from services.logger import info, warning, error

# Activity classification based on app name
ACTIVITY_MAP: dict[str, str] = {
    # Coding / Development
    "visual studio code": "coding",
    "code": "coding",
    "cursor": "coding",
    "vscodium": "coding",
    "windsurf": "coding",
    "xcode": "coding",
    "android studio": "coding",
    "intellij idea": "coding",
    "pycharm": "coding",
    "webstorm": "coding",
    "sublime text": "coding",
    "vim": "coding",
    "neovim": "coding",
    "iterm2": "coding",
    "terminal": "coding",
    "warp": "coding",
    # Browsing / Research
    "safari": "browsing",
    "google chrome": "browsing",
    "chrome": "browsing",
    "firefox": "browsing",
    "brave browser": "browsing",
    "edge": "browsing",
    "opera": "browsing",
    "arc": "browsing",
    "zen browser": "browsing",
    "orion": "browsing",
    # Reading / Documentation
    "notion": "reading",
    "obsidian": "reading",
    "notes": "reading",
    "bear": "reading",
    "readdle": "reading",
    "apple books": "reading",
    "kindle": "reading",
    "pdf expert": "reading",
    "adobe acrobat": "reading",
    # Communication
    "slack": "communication",
    "teams": "communication",
    "discord": "communication",
    "telegram": "communication",
    "whatsapp": "communication",
    "zoom": "communication",
    "google meet": "communication",
    "messenger": "communication",
    # Design / Creative
    "figma": "design",
    "sketch": "design",
    "photoshop": "design",
    "illustrator": "design",
    "blender": "design",
    "final cut": "design",
    "premiere": "design",
    "after effects": "design",
    # Other
    "spotify": "entertainment",
    "music": "entertainment",
}

# Window title keywords that override activity type
WINDOW_HINTS: list[tuple[list[str], str]] = [
    (["stackoverflow", "stack overflow", "github", "gitlab", "docs", "documentation", "mdn"], "reading"),
    (["youtube", "netflix", "twitch"], "entertainment"),
    (["terminal", "bash", "zsh", "ssh", "docker", "kubectl", "npm", "pip"], "coding"),
]


class RealActivityTracker:
    """
    Monitors actual macOS activity using AppleScript and system commands.
    Falls back to simulated activity when detection fails.
    """

    def __init__(
        self,
        event_bus: EventBus,
        use_simulation_fallback: bool = True,
    ) -> None:
        self._bus = event_bus
        self._use_fallback = use_simulation_fallback
        self._running = False
        self._thread: threading.Thread | None = None

        self._session_id = f"session_{int(time.time())}"
        self._last_activity_type = "idle"
        self._last_window = "unknown"
        self._last_active_time = time.time()
        self._total_idle = 0.0

    # ── Lifecycle ─────────────────────────────────────────────────────

    def start(self) -> None:
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        info(f"RealActivityTracker started (session_id={self._session_id})")

    def stop(self) -> None:
        self._running = False
        info("RealActivityTracker stopped")

    # ── macOS detection ───────────────────────────────────────────────

    @staticmethod
    def _get_frontmost_app() -> str | None:
        """Return the name of the frontmost application."""
        try:
            result = subprocess.run(
                [
                    "osascript",
                    "-e",
                    'tell application "System Events" to get name of first application process whose frontmost is true',
                ],
                capture_output=True,
                text=True,
                timeout=3,
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception:
            pass
        return None

    @staticmethod
    def _get_window_title(app_name: str) -> str | None:
        """Return the title of the frontmost window for the given app."""
        try:
            result = subprocess.run(
                [
                    "osascript",
                    "-e",
                    f'tell application "{app_name}" to get name of front window',
                ],
                capture_output=True,
                text=True,
                timeout=3,
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception:
            pass
        return None

    @staticmethod
    def _get_idle_time() -> float:
        """Return seconds since last user input (keyboard/mouse)."""
        try:
            result = subprocess.run(
                ["ioreg", "-c", "IOHIDSystem", "-r", "-d", "1"],
                capture_output=True,
                text=True,
                timeout=3,
            )
            for line in result.stdout.split("\n"):
                if "HIDIdleTime" in line:
                    # Value is in nanoseconds
                    ns_str = line.split("=")[-1].strip()
                    if ns_str.endswith("ms"):
                        ns = float(ns_str.replace("ms", "")) * 1_000_000
                    else:
                        ns = float(ns_str)
                    return ns / 1_000_000_000  # Convert to seconds
        except Exception:
            pass
        return 0.0

    @staticmethod
    def _classify_activity(app_name: str, window_title: str | None) -> str:
        """Classify activity type based on app name and window title."""
        app_lower = app_name.lower().strip()

        # Direct app → activity mapping
        for key, activity in ACTIVITY_MAP.items():
            if key in app_lower:
                return activity

        # Window title hints
        if window_title:
            wt_lower = window_title.lower()
            for keywords, activity in WINDOW_HINTS:
                for kw in keywords:
                    if kw in wt_lower:
                        return activity

        # Default for common productive apps
        productive_apps = ["finder", "system preferences", "settings"]
        if app_lower in productive_apps:
            return "reading"

        return "other"

    # ── Main loop ─────────────────────────────────────────────────────

    def _loop(self) -> None:
        consecutive_failures = 0
        use_simulated = False

        while self._running:
            delay = 3.0  # Check every 3 seconds

            try:
                idle_seconds = self._get_idle_time()

                # If user is idle for more than 60s, emit idle event
                if idle_seconds > 60:
                    if self._last_activity_type != "idle":
                        now = datetime.now(timezone.utc).isoformat()
                        payload = {
                            "timestamp": now,
                            "activity_type": "idle",
                            "previous_type": self._last_activity_type,
                            "window_name": self._last_window,
                            "session_id": self._session_id,
                            "duration": round(idle_seconds, 2),
                        }
                        self._last_activity_type = "idle"
                        self._bus.emit("activity.switch", payload)
                        self._bus.emit("activity.idle", payload)
                    time.sleep(delay)
                    continue

                # Get frontmost app
                app_name = self._get_frontmost_app()
                if not app_name:
                    consecutive_failures += 1
                    if self._use_fallback and consecutive_failures >= 3:
                        use_simulated = True
                        break
                    time.sleep(delay)
                    continue

                consecutive_failures = 0
                window_title = self._get_window_title(app_name)
                activity_type = self._classify_activity(app_name, window_title)
                now = datetime.now(timezone.utc).isoformat()

                payload = {
                    "timestamp": now,
                    "activity_type": activity_type,
                    "previous_type": self._last_activity_type,
                    "window_name": f"{app_name} - {window_title or 'unknown'}",
                    "session_id": self._session_id,
                    "duration": round(delay, 2),
                }

                if activity_type != self._last_activity_type:
                    self._bus.emit("activity.switch", payload)

                if activity_type == "idle":
                    self._bus.emit("activity.idle", payload)
                else:
                    self._bus.emit("activity.update", payload)

                self._last_activity_type = activity_type
                self._last_window = payload["window_name"]

            except Exception as e:
                error(f"RealActivityTracker error: {e}")
                time.sleep(delay)

        # Fallback to simulated tracker if real detection fails repeatedly
        if use_simulated:
            warning("Falling back to simulated activity tracker")
            self._run_simulated_fallback()

    # ── Simulated fallback ────────────────────────────────────────────

    def _run_simulated_fallback(self) -> None:
        """Simple simulated activity when real detection is unavailable."""
        from core.activity_tracker import ActivityTracker

        sim = ActivityTracker(self._bus)
        sim.start()
        # Keep the fallback running
        while self._running:
            time.sleep(1)
        sim.stop()
