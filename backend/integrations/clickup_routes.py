"""
ClickUp routes — API endpoints for ClickUp integration.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from integrations.clickup_service import ClickUpService

router = APIRouter(prefix="/integrations/clickup", tags=["clickup"])

# Singleton service instance (injected by main.py)
clickup_service: ClickUpService | None = None


# ── Request models ────────────────────────────────────────────────────


class ConnectRequest(BaseModel):
    token: str


# ── Endpoints ─────────────────────────────────────────────────────────


@router.get("/status")
async def get_status():
    """Check if ClickUp integration is configured and connected."""
    if clickup_service is None:
        return {"connected": False, "error": "Service not initialized"}
    return {"connected": clickup_service.is_connected()}


@router.post("/connect")
async def connect(req: ConnectRequest):
    """Connect to ClickUp with a personal API token."""
    if clickup_service is None:
        raise HTTPException(500, "Service not initialized")
    try:
        result = clickup_service.connect(req.token)
        return {"message": "Connected to ClickUp", **result}
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(500, f"Connection failed: {e}")


@router.post("/disconnect")
async def disconnect():
    """Disconnect and remove stored token."""
    if clickup_service is None:
        raise HTTPException(500, "Service not initialized")
    clickup_service.disconnect()
    return {"message": "Disconnected from ClickUp"}


@router.post("/sync")
async def sync():
    """Full sync: teams → spaces → folders → lists → tasks (en thread separado)."""
    import asyncio
    if clickup_service is None:
        raise HTTPException(500, "Service not initialized")
    try:
        result = await asyncio.to_thread(clickup_service.sync_all)
        return {"message": "Sync completed", **result}
    except RuntimeError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(500, f"Sync failed: {e}")


@router.get("/structure")
async def get_structure():
    """Get the full workspace hierarchy (cached)."""
    if clickup_service is None:
        raise HTTPException(500, "Service not initialized")
    try:
        return clickup_service.get_structure()
    except Exception as e:
        raise HTTPException(500, str(e))


@router.get("/tasks")
async def get_tasks(list_id: str | None = None, status: str | None = None, limit: int = 50):
    """Get cached tasks, optionally filtered by list or status."""
    if clickup_service is None:
        raise HTTPException(500, "Service not initialized")
    try:
        tasks = clickup_service.get_tasks(list_id=list_id, status=status, limit=limit)
        return {"count": len(tasks), "tasks": tasks}
    except Exception as e:
        raise HTTPException(500, str(e))


@router.get("/report")
async def generate_report():
    """Generate the end-of-day report crossing activity data with ClickUp tasks."""
    if clickup_service is None:
        raise HTTPException(500, "Service not initialized")
    try:
        report = clickup_service.generate_daily_report()
        return report
    except RuntimeError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(500, f"Report failed: {e}")
