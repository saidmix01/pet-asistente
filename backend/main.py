"""
Work Assistant Core — Entry point.
Initialises all layers and keeps the system alive.
"""

import asyncio
import threading

import uvicorn

from core.event_bus import EventBus
from core.system_state import SystemState
from core.event_stream import EventStream
from core.processor import Processor
from api.server import create_app
from db.database import init_db
from services.logger import info


def main() -> None:
    info("=== Work Assistant Core v1.0 starting ===")

    # Database
    init_db()

    # ClickUp cache tables
    from integrations.clickup_db import init_clickup_tables
    init_clickup_tables()

    # Daily log tables
    from integrations.daily_log import init_daily_log_tables
    init_daily_log_tables()

    # Time tracking tables
    from integrations.time_tracker import init_time_tracking_tables
    init_time_tracking_tables()

    # Event system
    bus = EventBus()

    # Live system state
    state = SystemState()

    # Event stream (WebSocket bridge)
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    stream = EventStream(bus, state, loop=loop)

    # ── Real activity monitoring (macOS) ─────────────────────────────
    from core.real_activity_tracker import RealActivityTracker
    tracker = RealActivityTracker(bus, use_simulation_fallback=True)

    # Processing layer
    from services.activity_service import ActivityService

    activity_service = ActivityService()
    processor = Processor(bus, activity_service, state, stream)

    # ── Time Tracker (measure actual time per task) ──────────────────
    from integrations.time_tracker import TimeTracker
    time_tracker = TimeTracker()

    # ── Task Tracker (auto-detect ClickUp status changes) ────────────
    from integrations.task_tracker import TaskTracker
    task_tracker = TaskTracker(poll_interval=60, time_tracker=time_tracker)

    # ── Git Detector ──────────────────────────────────────────────────
    from integrations.git_detector import GitDetector
    git_detector = GitDetector()

    # ── Auto Report (generates at 4pm) ────────────────────────────────
    from integrations.auto_report import AutoReport
    auto_report = AutoReport(task_tracker=task_tracker)

    # ── Start internal subsystems ─────────────────────────────────────
    processor.start()
    tracker.start()
    task_tracker.start()
    auto_report.start()

    # ── FastAPI ──────────────────────────────────────────────────────
    # Inject services into routes
    import integrations.auto_report_routes as ar_routes
    ar_routes.auto_report = auto_report
    ar_routes.task_tracker = task_tracker
    ar_routes.git_detector = git_detector
    ar_routes.time_tracker = time_tracker

    # Inject into AI routes
    import integrations.ai_routes as ai_routes_module
    ai_routes_module.time_tracker = time_tracker

    # Webhook handler available (for ClickUp webhook config if needed)
    # import integrations.clickup_webhooks as cw_routes
    # cw_routes.task_tracker = task_tracker

    app = create_app(state=state, stream=stream)

    # ── Start heartbeat loop on the same event loop ───────────────────
    def run_async_loop():
        asyncio.set_event_loop(loop)
        loop.run_until_complete(stream.heartbeat_loop(interval=5.0))

    hb_thread = threading.Thread(target=run_async_loop, daemon=True)
    hb_thread.start()

    info("Work Assistant Core v1.0 running on http://127.0.0.1:8000")
    info("WebSocket endpoint: ws://127.0.0.1:8000/ws/state")
    info("ClickUp integration ready")
    info("Real activity monitoring active (macOS)")
    info("Task Tracker active (polling ClickUp every 60s)")
    info("Time Tracker active (measuring hours per task)")
    info("Auto Report will generate at 4:00 PM")

    uvicorn.run(
        app,
        host="127.0.0.1",
        port=8000,
        log_level="warning",
    )


if __name__ == "__main__":
    main()
