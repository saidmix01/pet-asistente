"""
Logger service — simple structured logging with levels.
"""

import sys
from datetime import datetime, timezone


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def _log(level: str, message: str) -> None:
    line = f"[{level}] [{_timestamp()}] {message}"
    print(line, file=sys.stderr, flush=True)


def info(msg: str) -> None:
    _log("INFO", msg)


def warning(msg: str) -> None:
    _log("WARNING", msg)


def error(msg: str) -> None:
    _log("ERROR", msg)
