"""
Due Soon / Next Task — endpoints for due reminders and suggestions.
"""

from datetime import datetime, timezone, timedelta
from fastapi import APIRouter

from integrations.clickup_db import get_cached_tasks

router = APIRouter(prefix="/integrations/clickup", tags=["clickup"])


@router.get("/tasks-due-soon")
async def tasks_due_soon(hours: float = 2.0):
    """
    Return tasks with due_date within the next N hours (default 2h).
    Also includes overdue tasks.
    """
    tasks = get_cached_tasks(limit=200)
    now = datetime.now(timezone.utc).timestamp() * 1000
    soon_limit = now + (hours * 3600 * 1000)

    due_soon = []
    for t in tasks:
        due_str = t.get("due_date")
        status = (t.get("status") or "").lower()
        if not due_str or status in ("done", "closed", "completed"):
            continue
        try:
            due_ms = int(due_str)
        except (ValueError, TypeError):
            continue
        # Overdue or due within hours
        if due_ms <= soon_limit:
            is_overdue = due_ms < now
            remaining_h = round((due_ms - now) / 3600 / 1000, 1) if not is_overdue else 0
            due_soon.append({
                "id": t["id"],
                "name": t["name"],
                "project": t.get("project_name", ""),
                "status": t.get("status", ""),
                "due_date": due_str,
                "overdue": is_overdue,
                "remaining_hours": remaining_h,
            })

    due_soon.sort(key=lambda x: x.get("remaining_hours", 0) if not x["overdue"] else -999)
    return {"count": len(due_soon), "tasks": due_soon}


@router.get("/next-task")
async def next_task():
    """
    Suggest the next task to work on based on priority and status.
    Returns the highest-priority task that isn't done/closed.
    """
    tasks = get_cached_tasks(limit=200)
    now = datetime.now(timezone.utc).timestamp() * 1000

    # Filter out completed tasks
    active = [t for t in tasks if (t.get("status") or "").lower() not in ("done", "closed", "completed")]

    if not active:
        return {"task": None, "message": "No hay tareas pendientes 🎉"}

    # Sort by: overdue first, then priority, then due date
    def sort_key(t):
        status = (t.get("status") or "").lower()
        priority = t.get("priority")
        due_str = t.get("due_date")

        # Priority score: high=0, normal=1, low=2, none=3
        prio_score = 3
        if priority == 1: prio_score = 0  # urgent
        elif priority == 2: prio_score = 1  # high
        elif priority == 3: prio_score = 2  # normal

        # Overdue bonus
        overdue = 0
        if due_str:
            try:
                if int(due_str) < now:
                    overdue = -10  # overdue tasks go first
            except:
                pass

        # in progress before todo
        in_progress = 0 if "progress" in status or "review" in status else 1

        return (overdue, in_progress, prio_score)

    best = min(active, key=sort_key)
    status = best.get("status", "")
    due_str = best.get("due_date", "")
    due_info = ""
    if due_str:
        try:
            due_ms = int(due_str)
            remaining = (due_ms - now) / 3600 / 1000
            if remaining < 0:
                due_info = f" (vencida hace {abs(round(remaining, 1))}h)"
            else:
                due_info = f" (vence en {round(remaining, 1)}h)"
        except:
            pass

    return {
        "task": {
            "id": best["id"],
            "name": best["name"],
            "project": best.get("project_name", ""),
            "status": status,
            "priority": best.get("priority"),
            "due": due_info or "",
        },
        "message": f"Sugerencia: {best.get('project_name', '')} › {best['name']}{due_info}"
    }
