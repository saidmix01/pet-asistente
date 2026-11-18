"""
Platform detection — determines current OS and provides the right
activity tracker implementation.
"""

import json
import os
import platform
import re
import subprocess
import threading
import time
from datetime import datetime, timezone
from typing import Any

from core.event_bus import EventBus
from services.logger import info, warning, error

# Activity classification (shared across all platforms)
ACTIVITY_MAP: dict[str, str] = {
    "visual studio code": "coding", "code": "coding", "cursor": "coding",
    "vscodium": "coding", "windsurf": "coding", "xcode": "coding",
    "android studio": "coding", "intellij idea": "coding", "idea": "coding",
    "pycharm": "coding", "webstorm": "coding", "sublime text": "coding",
    "sublime_text": "coding", "vim": "coding", "nvim": "coding",
    "neovim": "coding", "iterm2": "coding", "terminal": "coding",
    "warp": "coding", "windows terminal": "coding", "windowsterminal": "coding",
    "powershell": "coding", "pwsh": "coding", "cmd": "coding",
    "devenv": "coding", "notepad++": "coding",
    "gnome-terminal": "coding", "konsole": "coding", "kitty": "coding",
    "alacritty": "coding", "wezterm": "coding", "foot": "coding",
    "tilix": "coding", "xfce4-terminal": "coding", "mate-terminal": "coding",
    "cutefish-terminal": "coding", "xterm": "coding", "kiro": "coding",
    "safari": "browsing", "google chrome": "browsing", "chrome": "browsing",
    "chromium": "browsing", "firefox": "browsing", "brave browser": "browsing",
    "brave": "browsing", "edge": "browsing", "msedge": "browsing",
    "opera": "browsing", "arc": "browsing", "zen browser": "browsing",
    "zen": "browsing", "vivaldi": "browsing", "microsoft edge": "browsing",
    "notion": "reading", "obsidian": "reading", "notes": "reading",
    "adobe acrobat": "reading", "pdf expert": "reading", "okular": "reading",
    "evince": "reading", "winword": "reading", "excel": "reading",
    "powerpnt": "reading", "libreoffice": "reading", "soffice": "reading",
    "slack": "communication", "teams": "communication", "ms-teams": "communication",
    "discord": "communication", "telegram": "communication", "whatsapp": "communication",
    "zoom": "communication", "google meet": "communication", "outlook": "communication",
    "thunderbird": "communication",
    "figma": "design", "sketch": "design", "photoshop": "design",
    "gimp": "design", "inkscape": "design", "blender": "design",
    "spotify": "entertainment", "music": "entertainment", "vlc": "entertainment",
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
    productive = [
        "finder", "system preferences", "settings", "explorer",
        "nemo", "nautilus", "thunar", "dolphin", "pcmanfm", "cutefish-filemanager",
    ]
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
            return _windows_idle_time()
        elif os_name == "linux":
            return _linux_idle_time()
    except Exception:
        pass
    return 0.0


_linux_xss_supported: bool | None = None
_x11_idle_bindings: tuple | None = None
_has_xprintidle: bool | None = None
_has_xdotool: bool | None = None


def _get_x11_idle_bindings():
    global _x11_idle_bindings, _linux_xss_supported
    if _x11_idle_bindings is not None:
        return _x11_idle_bindings
    if _linux_xss_supported is False:
        return None
    try:
        import ctypes

        class XScreenSaverInfo(ctypes.Structure):
            _fields_ = [
                ("window", ctypes.c_ulong),
                ("state", ctypes.c_int),
                ("kind", ctypes.c_int),
                ("til_or_since", ctypes.c_ulong),
                ("idle", ctypes.c_ulong),
                ("event_mask", ctypes.c_ulong),
            ]

        xlib = ctypes.cdll.LoadLibrary("libX11.so.6")
        xss = ctypes.cdll.LoadLibrary("libXss.so.1")
        xlib.XOpenDisplay.argtypes = [ctypes.c_char_p]
        xlib.XOpenDisplay.restype = ctypes.c_void_p
        xlib.XDefaultRootWindow.argtypes = [ctypes.c_void_p]
        xlib.XDefaultRootWindow.restype = ctypes.c_ulong
        xlib.XCloseDisplay.argtypes = [ctypes.c_void_p]
        xlib.XFree.argtypes = [ctypes.c_void_p]
        xss.XScreenSaverQueryExtension.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_int),
            ctypes.POINTER(ctypes.c_int),
        ]
        xss.XScreenSaverQueryExtension.restype = ctypes.c_int
        xss.XScreenSaverAllocInfo.restype = ctypes.POINTER(XScreenSaverInfo)
        xss.XScreenSaverQueryInfo.argtypes = [
            ctypes.c_void_p,
            ctypes.c_ulong,
            ctypes.POINTER(XScreenSaverInfo),
        ]
        xss.XScreenSaverQueryInfo.restype = ctypes.c_int

        _x11_idle_bindings = (xlib, xss, XScreenSaverInfo)
        return _x11_idle_bindings
    except Exception:
        _linux_xss_supported = False
        return None


def _linux_idle_time() -> float:
    """Get idle time on Linux via xprintidle, GNOME Mutter DBus, or X11 libXss."""
    global _linux_xss_supported, _has_xprintidle

    # 1. Try xprintidle (only if detected)
    if _has_xprintidle is not False:
        try:
            result = subprocess.run(
                ["xprintidle"],
                capture_output=True, text=True, timeout=2,
            )
            if result.returncode == 0 and result.stdout.strip():
                _has_xprintidle = True
                return float(result.stdout.strip()) / 1000.0
            else:
                _has_xprintidle = False
        except (FileNotFoundError, subprocess.SubprocessError, ValueError, OSError):
            _has_xprintidle = False

    # 2. Try GNOME Mutter IdleMonitor over D-Bus (works on GNOME Wayland & X11)
    try:
        result = subprocess.run(
            [
                "gdbus", "call", "--session",
                "--dest", "org.gnome.Mutter.IdleMonitor",
                "--object-path", "/org/gnome/Mutter/IdleMonitor/Core",
                "--method", "org.gnome.Mutter.IdleMonitor.GetIdletime",
            ],
            capture_output=True, text=True, timeout=2,
        )
        if result.returncode == 0 and result.stdout:
            m = re.search(r"(\d+)", result.stdout)
            if m:
                return float(m.group(1)) / 1000.0
    except (FileNotFoundError, subprocess.SubprocessError, ValueError, OSError):
        pass

    # 3. Try X11 libXss via cached ctypes when DISPLAY is available
    if os.environ.get("DISPLAY") and _linux_xss_supported is not False:
        bindings = _get_x11_idle_bindings()
        if bindings:
            xlib, xss, XScreenSaverInfo = bindings
            try:
                dpy = xlib.XOpenDisplay(None)
                if dpy:
                    try:
                        ev_base = ctypes.c_int()
                        err_base = ctypes.c_int()
                        if not xss.XScreenSaverQueryExtension(dpy, ctypes.byref(ev_base), ctypes.byref(err_base)):
                            _linux_xss_supported = False
                            return 0.0
                        _linux_xss_supported = True
                        root = xlib.XDefaultRootWindow(dpy)
                        info_ptr = xss.XScreenSaverAllocInfo()
                        if info_ptr:
                            try:
                                if xss.XScreenSaverQueryInfo(dpy, root, info_ptr):
                                    return float(info_ptr.contents.idle) / 1000.0
                            finally:
                                xlib.XFree(info_ptr)
                    finally:
                        xlib.XCloseDisplay(dpy)
            except Exception:
                _linux_xss_supported = False

    return 0.0


def _windows_idle_time() -> float:
    """Get idle time on Windows using ctypes (fast, no PowerShell)."""
    import ctypes
    import ctypes.wintypes

    class LASTINPUTINFO(ctypes.Structure):
        _fields_ = [
            ("cbSize", ctypes.wintypes.UINT),
            ("dwTime", ctypes.wintypes.DWORD),
        ]

    lii = LASTINPUTINFO()
    lii.cbSize = ctypes.sizeof(LASTINPUTINFO)
    if ctypes.windll.user32.GetLastInputInfo(ctypes.byref(lii)):
        millis = (ctypes.windll.kernel32.GetTickCount() - lii.dwTime) & 0xFFFFFFFF
        return millis / 1000.0
    return 0.0


def get_active_window_info() -> tuple[str | None, str | None]:
    """
    Return (app_name, window_title) for the currently focused window.
    Cross-platform: macOS (AppleScript), Windows (Win32 ctypes), Linux (xdotool/xprop/Wayland).
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
    """Get active window on Windows using ctypes (fast, no PowerShell)."""
    import ctypes
    import ctypes.wintypes

    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    psapi = ctypes.windll.psapi

    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return None, None

    # Get window title
    length = user32.GetWindowTextLengthW(hwnd) + 1
    buf = ctypes.create_unicode_buffer(length)
    user32.GetWindowTextW(hwnd, buf, length)
    window_title = buf.value or None

    # Get process name
    pid = ctypes.wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))

    app_name = "unknown"
    # Prefer PROCESS_QUERY_LIMITED_INFORMATION (works for elevated/UWP apps too)
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
    if handle:
        try:
            size = ctypes.wintypes.DWORD(1024)
            exe_buf = ctypes.create_unicode_buffer(1024)
            if kernel32.QueryFullProcessImageNameW(handle, 0, exe_buf, ctypes.byref(size)):
                base = os.path.basename(exe_buf.value)
                app_name = base[:-4] if base.lower().endswith(".exe") else base
        finally:
            kernel32.CloseHandle(handle)

    if app_name == "unknown":
        PROCESS_QUERY_INFORMATION = 0x0400
        PROCESS_VM_READ = 0x0010
        handle = kernel32.OpenProcess(PROCESS_QUERY_INFORMATION | PROCESS_VM_READ, False, pid.value)
        if handle:
            try:
                mod_buf = ctypes.create_unicode_buffer(260)
                if psapi.GetModuleBaseNameW(handle, None, mod_buf, 260):
                    base = mod_buf.value
                    app_name = base[:-4] if base.lower().endswith(".exe") else base
            finally:
                kernel32.CloseHandle(handle)

    return app_name, window_title


def _proc_name_from_pid(pid_str: str) -> str | None:
    """Read Linux process name from /proc/<pid>/comm."""
    try:
        with open(f"/proc/{pid_str.strip()}/comm", encoding="utf-8", errors="replace") as f:
            name = f.read().strip()
            return name or None
    except Exception:
        return None


def _linux_active_window() -> tuple[str | None, str | None]:
    """Get active window on Linux via xdotool, xprop, or Wayland compositor tools."""
    global _has_xdotool
    # 1. Try xdotool (only if installed and DISPLAY is set)
    if os.environ.get("DISPLAY") and _has_xdotool is not False:
        try:
            app_result = subprocess.run(
                ["xdotool", "getactivewindow", "getwindowname"],
                capture_output=True, text=True, timeout=2,
            )
            if app_result.returncode == 0 and app_result.stdout.strip():
                _has_xdotool = True
                title = app_result.stdout.strip()
                app_name = "unknown"
                try:
                    pid_result = subprocess.run(
                        ["xdotool", "getactivewindow", "getwindowpid"],
                        capture_output=True, text=True, timeout=2,
                    )
                    if pid_result.returncode == 0 and pid_result.stdout.strip():
                        app_name = _proc_name_from_pid(pid_result.stdout) or "unknown"
                except (FileNotFoundError, subprocess.SubprocessError, OSError):
                    pass
                return app_name, title
            else:
                _has_xdotool = False
        except (FileNotFoundError, subprocess.SubprocessError, OSError):
            _has_xdotool = False

        # 2. Fallback to xprop (X11 / XWayland)
        try:
            result = subprocess.run(
                ["xprop", "-root", "_NET_ACTIVE_WINDOW"],
                capture_output=True, text=True, timeout=2,
            )
            if result.returncode == 0:
                match = re.search(r"0x[0-9a-fA-F]+", result.stdout)
                if match and match.group() != "0x0":
                    wid = match.group()
                    props = subprocess.run(
                        ["xprop", "-id", wid, "_NET_WM_NAME", "WM_NAME", "WM_CLASS", "_NET_WM_PID"],
                        capture_output=True, text=True, timeout=2,
                    )
                    if props.returncode == 0:
                        out = props.stdout
                        title = None
                        app_name = None

                        for prop_name in ("_NET_WM_NAME", "WM_NAME"):
                            m = re.search(rf'^{prop_name}\([^)]+\)\s*=\s*"(.*)"$', out, re.MULTILINE)
                            if m and m.group(1):
                                title = m.group(1)
                                break

                        pid_m = re.search(r"_NET_WM_PID\([^)]+\)\s*=\s*(\d+)", out)
                        if pid_m:
                            app_name = _proc_name_from_pid(pid_m.group(1))

                        if not app_name:
                            cls_m = re.search(r'WM_CLASS\([^)]+\)\s*=\s*"([^"]+)"(?:,\s*"([^"]+)")?', out)
                            if cls_m:
                                app_name = cls_m.group(2) or cls_m.group(1)

                        if app_name or title:
                            return app_name or "unknown", title
        except (FileNotFoundError, subprocess.SubprocessError, OSError):
            pass

    # 3. Wayland compositor fallbacks
    # Hyprland
    if os.environ.get("HYPRLAND_INSTANCE_SIGNATURE"):
        try:
            res = subprocess.run(
                ["hyprctl", "activewindow", "-j"],
                capture_output=True, text=True, timeout=2,
            )
            if res.returncode == 0 and res.stdout.strip():
                data = json.loads(res.stdout)
                app_name = data.get("class") or data.get("initialClass")
                title = data.get("title")
                if app_name or title:
                    return app_name or "unknown", title
        except (FileNotFoundError, subprocess.SubprocessError, ValueError, OSError):
            pass

    # Sway / i3
    if os.environ.get("SWAYSOCK"):
        try:
            res = subprocess.run(
                ["swaymsg", "-t", "get_tree"],
                capture_output=True, text=True, timeout=2,
            )
            if res.returncode == 0 and res.stdout.strip():
                def _find_focused(node: dict) -> dict | None:
                    if node.get("focused"):
                        return node
                    for child in node.get("nodes", []) + node.get("floating_nodes", []):
                        found = _find_focused(child)
                        if found:
                            return found
                    return None

                focused = _find_focused(json.loads(res.stdout))
                if focused:
                    app_name = focused.get("app_id") or (focused.get("window_properties") or {}).get("class")
                    title = focused.get("name")
                    if app_name or title:
                        return app_name or "unknown", title
        except (FileNotFoundError, subprocess.SubprocessError, ValueError, OSError):
            pass

    # KDE Wayland (kdotool if installed)
    try:
        res = subprocess.run(
            ["kdotool", "getactivewindow", "getwindowname"],
            capture_output=True, text=True, timeout=2,
        )
        if res.returncode == 0 and res.stdout.strip():
            title = res.stdout.strip()
            cls_res = subprocess.run(
                ["kdotool", "getactivewindow", "getwindowclassname"],
                capture_output=True, text=True, timeout=2,
            )
            app_name = cls_res.stdout.strip() if cls_res.returncode == 0 and cls_res.stdout.strip() else "unknown"
            return app_name, title
    except (FileNotFoundError, subprocess.SubprocessError, OSError):
        pass

    return None, None


def get_active_window_geometry() -> dict | None:
    """
    Return geometry for the active window:
    {"x": int, "y": int, "width": int, "height": int, "title": str, "app": str}
    """
    os_name = get_os()
    try:
        if os_name == "windows":
            user32 = ctypes.windll.user32
            hwnd = user32.GetForegroundWindow()
            if hwnd:
                rect = ctypes.wintypes.RECT()
                if user32.GetWindowRect(hwnd, ctypes.byref(rect)):
                    app_name, title = _windows_active_window()
                    return {
                        "x": rect.left,
                        "y": rect.top,
                        "width": max(100, rect.right - rect.left),
                        "height": max(100, rect.bottom - rect.top),
                        "title": title or "",
                        "app": app_name or "",
                    }
        elif os_name == "linux" and os.environ.get("DISPLAY"):
            res = subprocess.run(
                ["xprop", "-root", "_NET_ACTIVE_WINDOW"],
                capture_output=True, text=True, timeout=2,
            )
            if res.returncode == 0:
                m = re.search(r"0x[0-9a-fA-F]+", res.stdout)
                if m and m.group() != "0x0":
                    wid = m.group()
                    info_res = subprocess.run(
                        ["xwininfo", "-id", wid],
                        capture_output=True, text=True, timeout=2,
                    )
                    if info_res.returncode == 0:
                        out = info_res.stdout
                        x_m = re.search(r"Absolute upper-left X:\s+(-?\d+)", out)
                        y_m = re.search(r"Absolute upper-left Y:\s+(-?\d+)", out)
                        w_m = re.search(r"Width:\s+(\d+)", out)
                        h_m = re.search(r"Height:\s+(\d+)", out)
                        app_name, title = _linux_active_window()
                        if x_m and y_m and w_m and h_m:
                            return {
                                "x": int(x_m.group(1)),
                                "y": int(y_m.group(1)),
                                "width": int(w_m.group(1)),
                                "height": int(h_m.group(1)),
                                "title": title or "",
                                "app": app_name or "",
                            }
    except Exception as e:
        error(f"get_active_window_geometry failed: {e}")
    return None


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
                time.sleep(delay)

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
