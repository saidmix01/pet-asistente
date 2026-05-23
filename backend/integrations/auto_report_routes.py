"""
Auto Report routes — API endpoints for saved reports, git activity, active tasks.
"""

from datetime import date

from fastapi import APIRouter, HTTPException, Query

router = APIRouter(prefix="/report", tags=["report"])

# Injected by main.py
auto_report = None
task_tracker = None
git_detector = None
time_tracker = None


@router.post("/generate")
async def generate_report_now():
    """Force-generate today's report immediately."""
    if auto_report is None:
        raise HTTPException(500, "AutoReport not initialized")
    filepath = auto_report.generate_today_report()
    return {"message": "Report generated", "file": filepath}


@router.get("/saved")
async def list_saved_reports():
    """List all saved daily reports."""
    if auto_report is None:
        raise HTTPException(500, "AutoReport not initialized")
    return {"reports": auto_report.list_reports()}


@router.get("/saved/{date_str}")
async def get_saved_report(date_str: str):
    """Get a specific saved report by date (YYYY-MM-DD)."""
    if auto_report is None:
        raise HTTPException(500, "AutoReport not initialized")
    report = auto_report.get_report(date_str)
    if not report:
        raise HTTPException(404, f"No report found for {date_str}")
    return report


@router.get("/active-tasks")
async def get_active_tasks():
    """Get tasks currently being worked on (detected by TaskTracker)."""
    if task_tracker is None:
        return {"tasks": []}
    return {
        "current": task_tracker.get_current_task(),
        "all_active": task_tracker.get_active_tasks(),
    }


@router.get("/git-activity")
async def get_git_activity():
    """Get git repositories activity detected today."""
    if git_detector is None:
        return {"repos": []}
    try:
        activity = git_detector.get_git_summary()
        return {"repos": activity}
    except Exception as e:
        raise HTTPException(500, f"Git scan failed: {e}")


@router.get("/time-tracking")
async def get_time_tracking():
    """Get time tracking data for today."""
    if time_tracker is None:
        return {"entries": [], "projects": {}}
    return {
        "current_task_id": time_tracker.get_current_task_id(),
        "is_tracking": time_tracker.is_tracking(),
        "current_duration": time_tracker.get_current_duration(),
        "entries": time_tracker.get_today_entries(),
        "project_summary": time_tracker.get_project_time_summary(),
    }
