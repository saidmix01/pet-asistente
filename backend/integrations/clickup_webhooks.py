"""
ClickUp Webhook handler — receives real-time task updates from ClickUp.
Processes events: status changes, description updates, checklist changes.
"""

from fastapi import APIRouter, Request, HTTPException
from datetime import date

from integrations.daily_log import add_log_entry

router = APIRouter(prefix="/integrations/clickup", tags=["clickup"])

# Injected by main.py
task_tracker = None


@router.post("/webhook")
async def clickup_webhook(request: Request):
    """
    Receive webhook events from ClickUp.
    Events: taskCreated, taskUpdated, taskStatusUpdated, taskCommentPosted
    """
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(400, "Invalid JSON")

    event = body.get("event", "")
    task_data = body.get("task", {})
    history = body.get("history_items", [])

    if not task_data:
        return {"ok": True, "message": "No task data"}

    task_id = task_data.get("id", "")
    task_name = task_data.get("name", "")
    status_obj = task_data.get("status", {})
    status = (status_obj.get("status", "") if status_obj else "").lower()
    description = task_data.get("description", "") or ""
    project = task_data.get("project", {}) or {}
    project_name = project.get("name", "") if isinstance(project, dict) else ""
    list_obj = task_data.get("list", {}) or {}
    list_name = list_obj.get("name", "") if isinstance(list_obj, dict) else ""

    today = date.today().isoformat()

    if event in ("taskStatusUpdated", "taskUpdated"):
        # Check history items for status change
        status_changed = any(
            h.get("field") == "status" for h in history if isinstance(h, dict)
        )

        if status_changed or event == "taskStatusUpdated":
            # Determine if it's active or completed
            from integrations.task_tracker import ACTIVE_STATUSES, COMPLETED_STATUSES
            progress = 50 if status in ACTIVE_STATUSES else (100 if status in COMPLETED_STATUSES else 0)

            notes_parts = []
            if description:
                notes_parts.append(description[:500])

            # Check for checklists in the payload
            checklists = task_data.get("checklists", [])
            if checklists:
                cl_lines = []
                for cl in checklists:
                    items = cl.get("items", [])
                    done = sum(1 for i in items if i.get("resolved", False))
                    total = len(items)
                    cl_lines.append(f"Checklist: {done}/{total}")
                    for i in items:
                        if i.get("resolved", False):
                            cl_lines.append(f"  ✅ {i.get('name', '')}")
                if cl_lines:
                    notes_parts.append("\n".join(cl_lines))

            if not notes_parts:
                notes_parts.append(f"Status changed: {status}")

            add_log_entry(
                date=today,
                clickup_task_id=task_id,
                project_name=project_name,
                list_name=list_name,
                task_name=task_name,
                progress=progress,
                description="\n".join(notes_parts),
            )

    return {"ok": True}
