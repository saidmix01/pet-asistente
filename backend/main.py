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
    info("=== Work Assistant Core v1.2 starting ===")

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

    # Chat history tables
    from integrations.chat_history import init_chat_tables
    init_chat_tables()

    # Pomodoro tables
    from integrations.pomodoro import init_pomodoro_tables
    init_pomodoro_tables()

    # Event system
    bus = EventBus()

    # ── Verify ClickUp connection on startup ─────────────────────────
    from integrations.clickup_config import load_token
    _cu_token = load_token()
    if _cu_token:
        info(f"ClickUp token found (length={len(_cu_token)})")
    else:
        info("ClickUp token NOT found — notifications disabled")

    # Live system state
    state = SystemState()

    # Event stream (WebSocket bridge)
    stream = EventStream(bus, state)

    # ── Real activity monitoring (cross-platform) ────────────────────
    from core.platform_detector import CrossPlatformTracker, get_os
    from services.config_store import get_simulate_activity
    tracker = CrossPlatformTracker(bus, use_simulation_fallback=get_simulate_activity())
    info(f"Activity monitoring active ({get_os().upper()}, simulation_fallback={get_simulate_activity()})")

    # Processing layer
    from services.activity_service import ActivityService

    activity_service = ActivityService()
    processor = Processor(bus, activity_service, state, stream)

    # ── Time Tracker (measure actual time per task) ──────────────────
    from integrations.time_tracker import TimeTracker
    time_tracker = TimeTracker()

    # ── Task Tracker (auto-detect ClickUp status changes) ────────────
    from integrations.task_tracker import TaskTracker
    task_tracker = TaskTracker(poll_interval=60, time_tracker=time_tracker, event_stream=stream)

    # ── Git Detector ──────────────────────────────────────────────────
    from integrations.git_detector import GitDetector
    git_detector = GitDetector()

    # ── Auto Report (generates at 4pm) ────────────────────────────────
    from integrations.auto_report import AutoReport
    auto_report = AutoReport(task_tracker=task_tracker, time_tracker=time_tracker)

    # ── Pet Brain (AI-driven autonomous behaviors & choreography) ────
    from core.pet_brain import PetBrain
    pet_brain = PetBrain(state=state, stream=stream, interval_seconds=45.0)

    # ── Start internal subsystems ─────────────────────────────────────
    processor.start()
    tracker.start()
    task_tracker.start()
    auto_report.start()
    pet_brain.start()

    # Notify brain on activity switch
    bus.subscribe(
        "activity.switch",
        lambda _ev, d: pet_brain.notify_event(f"activity_switch:{d.get('activity_type', '')}") if d else None,
    )

    # ── Background notification loop (pomodoro + clickup mentions) ────
    from integrations.pomodoro import check_pomodoro
    from integrations.clickup_mentions import MentionTracker
    from integrations.due_soon import get_due_soon_tasks

    mention_tracker = MentionTracker()

    import time as time_module

    def notification_loop():
        """Periodic checks for pomodoro completion, mentions, and overdue tasks."""
        # Wait for uvicorn's event loop to be available
        while stream._loop is None:
            time_module.sleep(1)

        last_mention_check = 0
        last_overdue_check = 0
        last_git_check = 0
        MENTION_INTERVAL = 60   # seconds (check every minute)
        OVERDUE_INTERVAL = 300  # seconds
        GIT_INTERVAL = 20      # seconds (live git watcher)

        while True:
            time_module.sleep(10)
            now = time_module.time()

            # Check pomodoro completion
            try:
                result = check_pomodoro()
                if result and result.get("completed"):
                    stream.on_event("pomodoro.completed", {
                        "session_count": result["session_count"],
                        "suggest": result["suggest"],
                    })
            except Exception:
                pass

            # Check ClickUp mentions periodically
            if now - last_mention_check > MENTION_INTERVAL:
                last_mention_check = now
                try:
                    new_mentions = mention_tracker.check_new_mentions()
                    for m in new_mentions:
                        stream.on_event("clickup.mention", m)
                except Exception:
                    pass

            # Check Git repositories for live commits and uncommitted alerts
            if now - last_git_check > GIT_INTERVAL:
                last_git_check = now
                try:
                    for git_ev in git_detector.check_live_events():
                        stream.on_event(git_ev["event"], git_ev["data"])
                except Exception:
                    pass

            # Check overdue tasks periodically
            if now - last_overdue_check > OVERDUE_INTERVAL:
                last_overdue_check = now
                try:
                    overdue = get_due_soon_tasks(hours=0)
                    for t in overdue:
                        stream.on_event("deadline.overdue", {
                            "task_id": t.get("id"),
                            "task_name": t.get("name"),
                            "due_date": t.get("due_date"),
                        })
                except Exception:
                    pass

    notif_thread = threading.Thread(target=notification_loop, daemon=True)
    notif_thread.start()

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
    ai_routes_module.pet_brain = pet_brain

    # Inject into chat routes
    import integrations.chat_routes as chat_routes_module
    chat_routes_module.time_tracker = time_tracker
    chat_routes_module.pet_brain = pet_brain

    # Inject into config routes
    import api.config_routes as config_routes_module
    config_routes_module.pet_brain = pet_brain

    # Inject into voice routes
    try:
        import integrations.voice_routes as voice_routes_module
        voice_routes_module.pet_brain = pet_brain
    except Exception:
        pass

    app = create_app(state=state, stream=stream)

    # ── Start heartbeat loop on the same event loop ───────────────────
    # Heartbeat will be started as a background task within uvicorn's event loop
    # via the FastAPI lifespan. We inject the stream into the app state.
    app.state.event_stream = stream

    info("Work Assistant Core v1.2 running on http://127.0.0.1:8000")
    info("WebSocket endpoint: ws://127.0.0.1:8000/ws/state")
    info("ClickUp integration ready")
    # info("Real activity monitoring active")  # ya se muestra arriba
    info("Task Tracker active (polling ClickUp every 60s)")
    info("Time Tracker active (measuring hours per task)")
    info("Chat history enabled (persistent conversations)")
    info("Pomodoro timer ready")
    info("Auto Report will generate at 4:00 PM")

    # Verify WebSocket support before starting
    try:
        import wsproto
        info(f"wsproto available: {wsproto.__version__}")
    except ImportError:
        info("WARNING: wsproto NOT available — WebSocket will NOT work!")
        try:
            import websockets
            info(f"websockets available: {websockets.__version__}")
        except ImportError:
            info("WARNING: websockets NOT available either!")

    uvicorn.run(
        app,
        host="127.0.0.1",
        port=8000,
        log_level="warning",
        ws="wsproto",
        http="h11",
    )


if __name__ == "__main__":
    main()
