"""
Logger service — structured logging to console + file in AppData.
"""

import os
import sys
from datetime import datetime, timezone

# Log file in AppData (Windows) or XDG data dir (Linux/macOS) when frozen
def _get_log_path() -> str:
    if getattr(sys, 'frozen', False):
        if os.name == 'nt':
            base = os.environ.get('APPDATA', os.path.expanduser('~'))
        else:
            base = os.environ.get('XDG_DATA_HOME', os.path.expanduser('~/.local/share'))
        log_dir = os.path.join(base, 'pet-asistente', 'logs')
    else:
        base = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
        log_dir = os.path.join(base, 'logs')
    os.makedirs(log_dir, exist_ok=True)
    today = datetime.now().strftime("%Y-%m-%d")
    return os.path.join(log_dir, f"pet-{today}.log")

_log_file = None

def _get_log_file():
    global _log_file
    if _log_file is None:
        try:
            _log_file = open(_get_log_path(), "a", encoding="utf-8")
        except Exception:
            _log_file = False  # Mark as failed, don't retry
    return _log_file if _log_file else None


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def _log(level: str, message: str) -> None:
    line = f"[{level}] [{_timestamp()}] {message}"
    print(line, file=sys.stderr, flush=True)
    # Also write to file
    f = _get_log_file()
    if f:
        try:
            f.write(line + "\n")
            f.flush()
        except Exception:
            pass


def info(msg: str) -> None:
    _log("INFO", msg)


def warning(msg: str) -> None:
    _log("WARNING", msg)


def error(msg: str) -> None:
    _log("ERROR", msg)
