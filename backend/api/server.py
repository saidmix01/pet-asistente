"""
FastAPI server factory — creates the Uvicorn server instance.
"""

import threading
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from api.routes import router as main_router
from integrations.clickup_routes import router as clickup_router
from integrations.due_soon import router as due_soon_router
from integrations.report_routes import router as report_router
from integrations.auto_report_routes import router as auto_report_router
from integrations.ai_routes import router as ai_router
from integrations.chat_routes import router as chat_router
from integrations.pomodoro import router as pomodoro_router
from integrations.clickup_service import ClickUpService
from core.system_state import SystemState
from core.event_stream import EventStream
from services.logger import info


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Auto-sync ClickUp on startup in background thread."""
    import integrations.clickup_routes as cu_routes
    svc = cu_routes.clickup_service
    if svc and svc.is_connected():
        info("ClickUp token found — auto-syncing in background...")
        threading.Thread(target=_do_sync, args=(svc,), daemon=True).start()
    else:
        info("ClickUp not configured — skipping auto-sync")
    yield


def _do_sync(svc):
    try:
        result = svc.sync_all(days_back=7)
        info(f"ClickUp sync complete: {result.get('tasks_synced', 0)} tasks")
    except Exception as e:
        info(f"ClickUp auto-sync failed: {e}")


def create_app(
    state: SystemState | None = None,
    stream: EventStream | None = None,
) -> FastAPI:
    app = FastAPI(
        title="Work Assistant Core",
        version="1.2.0",
        description="Local backend for monitoring, simulating and recording user activity.",
        lifespan=lifespan,
    )

    import api.routes as routes
    if state is not None:
        routes.system_state = state
    if stream is not None:
        routes.event_stream = stream

    import integrations.clickup_routes as cu_routes
    cu_routes.clickup_service = ClickUpService()

    # Inject time_tracker into chat routes
    import integrations.chat_routes as chat_routes_module
    import integrations.ai_routes as ai_routes_module
    # These will be set from main.py

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "http://192.168.1.6:5173",
            "http://192.168.1.6",
            "https://pet.devcloud.sbs",
            "null",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(main_router)
    app.include_router(clickup_router)
    app.include_router(due_soon_router)
    app.include_router(report_router)
    app.include_router(auto_report_router)
    app.include_router(ai_router)
    app.include_router(chat_router)
    app.include_router(pomodoro_router)
    return app
