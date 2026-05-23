"""
Daily Log routes — API endpoints for daily work logging linked to ClickUp.
"""

from datetime import date, timezone

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from integrations.daily_log import (
    init_daily_log_tables,
    add_log_entry,
    get_logs_by_date,
    get_recent_logs,
    delete_log_entry,
    generate_report,
)
from integrations.clickup_db import get_cached_tasks

router = APIRouter(prefix="/report", tags=["report"])


# ── Request models ────────────────────────────────────────────────────


class SubtaskEntry(BaseModel):
    name: str
    progress: int = 0


class LogEntryRequest(BaseModel):
    clickup_task_id: str = ""
    project_name: str = ""
    list_name: str = ""
    task_name: str = ""
    progress: int = 0
    description: str = ""
    subtasks: list[SubtaskEntry] = []


# ── Endpoints ─────────────────────────────────────────────────────────


@router.post("/log")
async def create_log_entry(entry: LogEntryRequest):
    """Add a daily log entry, optionally linked to a ClickUp task."""

    # If clickup_task_id is provided, auto-fill task data from cache
    if entry.clickup_task_id and not entry.task_name:
        tasks = get_cached_tasks(limit=500)
        matched = [t for t in tasks if t["id"] == entry.clickup_task_id]
        if matched:
            t = matched[0]
            entry.project_name = entry.project_name or t.get("project_name", "")
            entry.list_name = entry.list_name or ""
            entry.task_name = entry.task_name or t.get("name", "")

    if not entry.task_name:
        raise HTTPException(400, "task_name is required (or provide a valid clickup_task_id)")

    today = date.today().isoformat()
    subtasks_data = [{"name": s.name, "progress": s.progress} for s in entry.subtasks]

    entry_id = add_log_entry(
        date=today,
        clickup_task_id=entry.clickup_task_id,
        project_name=entry.project_name,
        list_name=entry.list_name,
        task_name=entry.task_name,
        progress=entry.progress,
        description=entry.description,
        subtasks=subtasks_data if subtasks_data else None,
    )
    return {"id": entry_id, "message": "Log entry added", "date": today}


@router.get("/log")
async def get_logs(
    date_str: str | None = Query(None, alias="date"),
    limit: int = 50,
):
    """Get log entries."""
    if date_str:
        logs = get_logs_by_date(date_str)
    else:
        logs = get_recent_logs(limit=limit)
    return {"count": len(logs), "logs": logs}


@router.delete("/log/{entry_id}")
async def delete_entry(entry_id: int):
    """Delete a log entry."""
    if delete_log_entry(entry_id):
        return {"message": "Entry deleted"}
    raise HTTPException(404, "Entry not found")


@router.get("/daily")
async def get_daily_report(date_str: str | None = Query(None, alias="date")):
    """Generate formatted daily report in ClickUp format."""
    today = date.today().isoformat()
    report_date = date_str or today
    report = generate_report(report_date)
    return {"date": report_date, "report": report}
