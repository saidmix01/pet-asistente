"""
Platform detection — determines current OS and provides the right
activity tracker implementation.
"""

import platform
import subprocess
import threading
import time
import random
from datetime import datetime, timezone
from typing import Any

from core.event_bus import EventBus
from services.logger import info, warning, error

# Activity classification (shared across all platforms)
ACTIVITY_MAP: dict[str, str] = {
    "visual studio code": "coding", "code": "coding", "cursor": "coding",
    "vscodium": "coding", "windsurf": "coding", "xcode": "coding",
    "android studio": "coding", "intellij idea": "coding", "pycharm": "coding",
    "webstorm": "coding", "sublime text": "coding", "vim": "coding",
    "neovim": "coding", "iterm2": "coding", "terminal": "coding",
    "warp": "coding", "windows terminal": "coding", "powershell": "coding",
    "cmd": "coding", "gnome-terminal": "coding", "konsole": "coding",
    "safari": "browsing", "google chrome": "browsing", "chrome": "browsing",
    "firefox": "browsing", "brave browser": "browsing", "edge": "browsing",
    "opera": "browsing", "arc": "browsing", "zen browser": "browsing",
    "microsoft edge": "browsing",
    "notion": "reading", "obsidian": "reading", "notes": "reading",
    "adobe acrobat": "reading", "pdf expert": "reading",
    "slack": "communication", "teams": "communication", "discord": "communication",
    "telegram": "communication", "whatsapp": "communication", "zoom": "communication",
    "google meet": "communication",
    "figma": "design", "sketch": "design", "photoshop": "design",
    "spotify": "entertainment", "music": "entertainment",
}

WINDOW_HINTS: list[tuple[list[str], str]] = [
    (["stackoverflow", "github", "gitlab", "docs", "documentation", "mdn"], "reading"),
    (["youtube", "netflix", "twitch"], "entertainment"),
    (["terminal", "bash", "zsh", "ssh", "docker", "kubectl", "npm", "pip"], "coding"),
]


def get_os() -> str:
    """Return 'windows', 'darwin', or 'linux'."""
    sys = platform.system().lower()
    if sys == "darwin":
        return "darwin"
    elif sys == "windows":
        return "windows"
    return "linux"


def classify_activity(app_name: str, window_title: str | None) -> str:
    """Classify activity type based on app name and window title."""
    app_lower = app_name.lower().strip()
    for key, activity in ACTIVITY_MAP.items():
        if key in app_lower:
            return activity
    if window_title:
        wt = window_title.lower()
        for keywords, activity in WINDOW_HINTS:
            for kw in keywords:
                if kw in wt:
                    return activity
    productive = ["finder", "system preferences", "settings", "explorer", "nemo", "nautilus", "thunar"]
    if app_lower in productive:
        return "reading"
    return "other"


def get_idle_time() -> float:
    """Return seconds since last user input (cross-platform)."""
    os_name = get_os()
    try:
        if os_name == "darwin":
            result = subprocess.run(
                ["ioreg", "-c", "IOHIDSystem", "-r", "-d", "1"],
                capture_output=True, text=True, timeout=3,
            )
            for line in result.stdout.split("\n"):
                if "HIDIdleTime" in line:
                    ns_str = line.split("=")[-1].strip()
                    ns = float(ns_str.replace("ms", "")) * 1_000_000 if "ms" in ns_str else float(ns_str)
                    return ns / 1_000_000_000
        elif os_name == "windows":
            result = subprocess.run(
                ["powershell", "-Command", "(Get-CimInstance Win32_Desktop).LastInputTime -as [DateTime]"],
                capture_output=True, text=True, timeout=3,
            )
            if result.returncode == 0 and result.stdout.strip():
                import datetime as dt
                last = dt.datetime.fromisoformat(result.stdout.strip())
                delta = dt.datetime.now() - last
                return delta.total_seconds()
        elif os_name == "linux":
            result = subprocess.run(
                ["xprintidle"],
                capture_output=True, text=True, timeout=3,
            )
            if result.returncode == 0 and result.stdout.strip():
                return float(result.stdout.strip()) / 1000
    except Exception:
        pass
    return 0.0


def get_active_window_info() -> tuple[str | None, str | None]:
    """
    Return (app_name, window_title) for the currently focused window.
    Cross-platform: macOS (AppleScript), Windows (PowerShell), Linux (xdotool).
    """
    os_name = get_os()
    try:
        if os_name == "darwin":
            return _macos_active_window()
        elif os_name == "windows":
            return _windows_active_window()
        elif os_name == "linux":
            return _linux_active_window()
    except Exception as e:
        error(f"get_active_window failed on {os_name}: {e}")
    return None, None


def _macos_active_window() -> tuple[str | None, str | None]:
    """Get active window on macOS via AppleScript."""
    app = subprocess.run(
        ["osascript", "-e", 'tell application "System Events" to get name of first application process whose frontmost is true'],
        capture_output=True, text=True, timeout=3,
    )
    app_name = app.stdout.strip() if app.returncode == 0 else None
    if not app_name:
        return None, None
    title = subprocess.run(
        ["osascript", "-e", f'tell application "{app_name}" to get name of front window'],
        capture_output=True, text=True, timeout=3,
    )
    window_title = title.stdout.strip() if title.returncode == 0 else None
    return app_name, window_title


def _windows_active_window() -> tuple[str | None, str | None]:
    """Get active window on Windows via PowerShell."""
    script = """
Add-Type @"
using System;
using System.Runtime.InteropServices;
using System.Text;
public class WinAPI {
    [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
    [DllImport("user32.dll")] public static extern int GetWindowText(IntPtr hWnd, StringBuilder text, int count);
    [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint pid);
}
"@
$hwnd = [WinAPI]::GetForegroundWindow()
$sb = New-Object System.Text.StringBuilder 256
[WinAPI]::GetWindowText($hwnd, $sb, 256)
$title = $sb.ToString()
$pid = 0
[WinAPI]::GetWindowThreadProcessId($hwnd, [ref]$pid)
$proc = Get-Process -Id $pid -ErrorAction SilentlyContinue
$app = if ($proc) { $proc.ProcessName } else { "unknown" }
Write-Output "$app|||$title"
"""
    result = subprocess.run(["powershell", "-NoProfile", "-Command", script],
                            capture_output=True, text=True, timeout=5)
    if result.returncode == 0 and "|||" in result.stdout:
        parts = result.stdout.strip().split("|||", 1)
        return parts[0].strip(), parts[1].strip() if len(parts) > 1 else None
    return None, None


def _linux_active_window() -> tuple[str | None, str | None]:
    """Get active window on Linux via xdotool/xprop."""
    # Try xdotool first
    app_result = subprocess.run(
        ["xdotool", "getactivewindow", "getwindowname"],
        capture_output=True, text=True, timeout=3,
    )
    if app_result.returncode == 0 and app_result.stdout.strip():
        title = app_result.stdout.strip()
        # Try to get PID and process name
        pid_result = subprocess.run(
            ["xdotool", "getactivewindow", "getwindowpid"],
            capture_output=True, text=True, timeout=3,
        )
        app_name = "unknown"
        if pid_result.returncode == 0 and pid_result.stdout.strip():
            try:
                import os as _os
                with open(f"/proc/{pid_result.stdout.strip()}/comm") as f:
                    app_name = f.read().strip()
            except Exception:
                pass
        return app_name, title

    # Fallback to xprop
    result = subprocess.run(
        ["xprop", "-root", "_NET_ACTIVE_WINDOW"],
        capture_output=True, text=True, timeout=3,
    )
    if result.returncode == 0:
        import re
        match = re.search(r"0x[0-9a-f]+", result.stdout)
        if match:
            wid = match.group()
            name_result = subprocess.run(
                ["xprop", "-id", wid, "WM_NAME"],
                capture_output=True, text=True, timeout=3,
            )
            if name_result.returncode == 0:
                m = re.search(r'"(.+)"', name_result.stdout)
                title = m.group(1) if m else None
                return "unknown", title
    return None, None


class CrossPlatformTracker:
    """
    Detects actual user activity on any OS (macOS, Windows, Linux).
    Falls back to simulation if detection fails.
    """

    def __init__(self, event_bus: EventBus, use_simulation_fallback: bool = True) -> None:
        self._bus = event_bus
        self._use_fallback = use_simulation_fallback
        self._running = False
        self._thread: threading.Thread | None = None
        self._session_id = f"session_{int(time.time())}"
        self._last_activity_type = "idle"
        self._last_window = "unknown"
        self._os_name = get_os()

    def start(self) -> None:
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        info(f"CrossPlatformTracker started (os={self._os_name}, session={self._session_id})")

    def stop(self) -> None:
        self._running = False
        info("CrossPlatformTracker stopped")

    def _loop(self) -> None:
        consecutive_failures = 0
        use_simulated = False

        while self._running:
            delay = 3.0  # Check every 3 seconds

            try:
                idle_seconds = get_idle_time()

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

                # Get active window
                app_name, window_title = get_active_window_info()
                if not app_name:
                    consecutive_failures += 1
                    if self._use_fallback and consecutive_failures >= 3:
                        use_simulated = True
                        break
                    time.sleep(delay)
                    continue

                consecutive_failures = 0
                activity_type = classify_activity(app_name, window_title)
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
                error(f"CrossPlatformTracker error: {e}")
                time.sleep(delay)

        if use_simulated:
            warning(f"Detection failed on {self._os_name}, falling back to simulated activity")
            self._run_simulated_fallback()

    def _run_simulated_fallback(self) -> None:
        from core.activity_tracker import ActivityTracker
        sim = ActivityTracker(self._bus)
        sim.start()
        while self._running:
            time.sleep(1)
        sim.stop()
