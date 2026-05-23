"""
Database models for the Work Assistant system.
"""

from dataclasses import dataclass


@dataclass
class ActivityRecord:
    """Represents a single activity record stored in SQLite."""

    id: int | None = None
    timestamp: str = ""
    activity_type: str = ""
    window_name: str = ""
    duration: float = 0.0
    session_id: str = ""
