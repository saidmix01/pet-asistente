"""
FastAPI routes for the Work Assistant API.
"""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from services.activity_service import ActivityService
from core.system_state import SystemState
from core.event_stream import EventStream

router = APIRouter()
service = ActivityService()

# Injected by main.py
system_state: SystemState | None = None
event_stream: EventStream | None = None

SYSTEM_STATUS = {"status": "active"}


# ── REST endpoints ───────────────────────────────────────────────────


@router.get("/")
async def system_status():
    return {"system": "Work Assistant Core", **SYSTEM_STATUS}


@router.get("/state")
async def get_live_state():
    if system_state is None:
        return {"error": "System state not initialized"}
    return system_state.get_state()


@router.get("/activities")
async def get_activities(limit: int = 20):
    records = service.get_recent(limit=limit)
    return {"count": len(records), "activities": [r.__dict__ for r in records]}


@router.get("/summary")
async def get_summary():
    data = service.get_today_summary()
    return {"date_summary": data}


# ── WebSocket endpoint ───────────────────────────────────────────────


@router.websocket("/ws/state")
async def websocket_state(ws: WebSocket):
    if event_stream is None:
        await ws.close(code=1011, reason="EventStream not initialized")
        return

    # Accept first, then connect to stream
    await ws.accept()
    try:
        await event_stream.connect(ws)
    except Exception:
        # If connect fails, close gracefully
        try:
            await ws.close()
        except Exception:
            pass
        return

    try:
        # Keep connection alive — read loop detects client disconnect
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    except RuntimeError as e:
        if "not connected" in str(e):
            pass
        else:
            raise
    finally:
        event_stream.disconnect(ws)
