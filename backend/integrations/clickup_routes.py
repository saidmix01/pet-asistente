"""
ClickUp routes — API endpoints for ClickUp integration.
"""

import urllib.error
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from integrations.clickup_service import ClickUpService

router = APIRouter(prefix="/integrations/clickup", tags=["clickup"])

# Singleton service instance (injected by main.py)
clickup_service: ClickUpService | None = None
task_tracker = None


# ── Request models ────────────────────────────────────────────────────


class ConnectRequest(BaseModel):
    token: str


# ── Endpoints ─────────────────────────────────────────────────────────


@router.get("/status")
async def get_status():
    """Check if ClickUp integration is configured and connected."""
    if clickup_service is None:
        return {"configured": False, "connected": False, "error": "Service not initialized"}
    configured = clickup_service.is_configured()
    connected = clickup_service.is_connected()
    return {
        "configured": configured,
        "connected": connected,
        "user_id": clickup_service._user_id,
        "username": getattr(clickup_service, "_username", None),
    }


@router.post("/connect")
async def connect(req: ConnectRequest):
    """Connect to ClickUp with a personal API token."""
    if clickup_service is None:
        raise HTTPException(500, "Service not initialized")
    try:
        result = clickup_service.connect(req.token)
        # Notify / restart task_tracker if running
        if task_tracker is not None:
            try:
                task_tracker.restart()
            except Exception as e:
                from services.logger import warning
                warning(f"TaskTracker restart after connect: {e}")
        return {"message": "Connected to ClickUp", **result}
    except urllib.error.HTTPError as e:
        if e.code == 401:
            raise HTTPException(401, "Token de ClickUp no autorizado o expirado (HTTP 401)")
        raise HTTPException(e.code, f"ClickUp API HTTP {e.code}: {e.reason}")
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        from services.logger import error
        error(f"ClickUp connect failed: {type(e).__name__}: {e}")
        raise HTTPException(500, f"Error de conexión con ClickUp: {e}")


@router.post("/disconnect")
async def disconnect():
    """Disconnect and remove stored token."""
    if clickup_service is None:
        raise HTTPException(500, "Service not initialized")
    clickup_service.disconnect()
    if task_tracker is not None:
        try:
            task_tracker.stop()
        except Exception:
            pass
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
