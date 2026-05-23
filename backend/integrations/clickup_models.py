"""
Database models for ClickUp integration (cached data).
"""

from dataclasses import dataclass


@dataclass
class CachedTeam:
    id: str
    name: str


@dataclass
class CachedSpace:
    id: str
    name: str
    team_id: str


@dataclass
class CachedFolder:
    id: str
    name: str
    space_id: str


@dataclass
class CachedList:
    id: str
    name: str
    folder_id: str | None
    space_id: str


@dataclass
class CachedTask:
    id: str
    name: str
    status: str
    description: str
    assignees: str  # JSON list
    tags: str  # JSON list
    priority: int | None
    due_date: str | None
    list_id: str
    project_name: str
    url: str
    updated_at: str
