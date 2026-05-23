"""
FastAPI server factory — creates the Uvicorn server instance.
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from api.routes import router as main_router
from integrations.clickup_routes import router as clickup_router
from integrations.report_routes import router as report_router
from integrations.auto_report_routes import router as auto_report_router
from integrations.ai_routes import router as ai_router
from integrations.clickup_service import ClickUpService
from integrations.clickup_config import load_token
from core.system_state import SystemState
from core.event_stream import EventStream
from services.logger import info


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Auto-sync ClickUp on startup if token is configured."""
    import integrations.clickup_routes as cu_routes
    svc = cu_routes.clickup_service
    if svc and svc.is_connected():
        info("ClickUp token found — auto-syncing...")
        try:
            result = svc.sync_all(days_back=7)
            info(f"ClickUp sync complete: {result.get('tasks_synced', 0)} tasks, {result.get('lists', 0)} lists")
        except Exception as e:
            info(f"ClickUp auto-sync failed (will retry on demand): {e}")
    else:
        info("ClickUp not configured — skipping auto-sync")
    yield


def create_app(
    state: SystemState | None = None,
    stream: EventStream | None = None,
) -> FastAPI:
    app = FastAPI(
        title="Work Assistant Core",
        version="1.1.0",
        description="Local backend for monitoring, simulating and recording user activity.",
        lifespan=lifespan,
    )

    # Inject dependencies into routes modules
    import api.routes as routes

    if state is not None:
        routes.system_state = state
    if stream is not None:
        routes.event_stream = stream

    # Inject ClickUp service
    import integrations.clickup_routes as cu_routes
    cu_routes.clickup_service = ClickUpService()

    app.include_router(main_router)
    app.include_router(clickup_router)
    app.include_router(report_router)
    app.include_router(auto_report_router)
    app.include_router(ai_router)
    return app
