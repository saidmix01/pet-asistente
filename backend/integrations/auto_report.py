"""
Auto Report — generates and saves the daily report at 4pm.
Combines: TaskTracker data + Git activity + Daily Log entries.
"""

import os
import json
import sys
import time
import threading
from datetime import datetime, timezone, date

from integrations.daily_log import get_logs_by_date, generate_report
from integrations.git_detector import GitDetector
from integrations.task_tracker import TaskTracker
from services.logger import info, warning, error


from db.database import get_data_dir

REPORTS_DIR = os.path.join(get_data_dir(), "daily_reports")


class AutoReport:
    """
    Generates and saves the daily report automatically at 4pm local time.
    Also available on demand via API.
    """

    def __init__(self, task_tracker: TaskTracker | None = None, time_tracker=None) -> None:
        self._task_tracker = task_tracker
        self._time_tracker = time_tracker
        self._running = False
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._running = True
        self._thread = threading.Thread(target=self._scheduler_loop, daemon=True)
        self._thread.start()
        info("AutoReport scheduler started (will generate at 4pm)")

    def stop(self) -> None:
        self._running = False
        info("AutoReport stopped")

    def _scheduler_loop(self) -> None:
        """Check every 60 seconds if it's 4pm."""
        while self._running:
            now = datetime.now()
            # At 4:00 PM generate the report (check within 60s window)
            if now.hour == 16 and now.minute == 0:
                # Only generate if not already generated today
                today = date.today().isoformat()
                filepath = os.path.join(REPORTS_DIR, f"report_{today}.json")
                if not os.path.exists(filepath):
                    self.generate_today_report()
                # Sleep 2 minutes to avoid regenerating
                time.sleep(120)
            time.sleep(60)

    # ── Generate report ───────────────────────────────────────────────

    def generate_today_report(self) -> str | None:
        """Generate and save today's report. Returns the filename."""
        today = date.today().isoformat()

        # 1. Get daily log entries
        logs = get_logs_by_date(today)

        # 2. Get git activity
        try:
            git = GitDetector()
            git_activity = git.get_git_summary()
        except Exception as e:
            warning(f"AutoReport: git scan failed: {e}")
            git_activity = []

        # 3. Get active tasks from tracker
        active_tasks = []
        if self._task_tracker:
            active_tasks = self._task_tracker.get_active_tasks()

        # 3b. Get time tracking data
        time_data = {}
        if self._time_tracker:
            try:
                time_data = self._time_tracker.get_project_time_summary()
            except Exception:
                pass

        # 4. Generate text report
        text_report = generate_report(today)

        # 5. Try AI enhancement using configured provider
        from services.ai import (
            is_antigravity_available,
            is_ollama_available,
            is_deepseek_configured,
            enhance_daily_report,
        )
        from services.config_store import get_ai_mode, get_deepseek_token

        ai_mode = get_ai_mode()
        deepseek_token = get_deepseek_token()
        ai_ready = (
            (ai_mode == "antigravity" and is_antigravity_available())
            or (ai_mode == "local" and is_ollama_available())
            or (ai_mode == "remote" and is_deepseek_configured(deepseek_token))
        )

        ai_enhanced = None
        if ai_ready:
            try:
                ai_data = {
                    "date": today,
                    "logs": logs,
                    "git_activity": git_activity,
                    "time_summary": time_data,
                    "raw_text": text_report,
                }
                ai_enhanced = enhance_daily_report(
                    ai_data,
                    mode=ai_mode,
                    api_token=deepseek_token,
                )
            except Exception:
                pass

        # 6. Build structured report
        report = {
            "date": today,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "text": text_report,
            "ai_enhanced": ai_enhanced,
            "entries": len(logs),
            "git_activity": git_activity,
            "active_tasks": active_tasks,
        }

        # 6. Save to file
        os.makedirs(REPORTS_DIR, exist_ok=True)
        filename = f"report_{today}.json"
        filepath = os.path.join(REPORTS_DIR, filename)

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)

        info(f"Daily report saved: {filepath}")

        # Also save a plaintext version
        txt_path = os.path.join(REPORTS_DIR, f"report_{today}.txt")
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write(text_report)

        return filepath

    # ── Load saved reports ────────────────────────────────────────────

    def get_report(self, report_date: str | None = None) -> dict | None:
        """Load a previously saved report."""
        target = report_date or date.today().isoformat()
        filepath = os.path.join(REPORTS_DIR, f"report_{target}.json")
        if os.path.exists(filepath):
            with open(filepath, encoding="utf-8") as f:
                return json.load(f)
        return None

    def list_reports(self) -> list[str]:
        """List all saved report dates."""
        os.makedirs(REPORTS_DIR, exist_ok=True)
        reports = []
        for fname in sorted(os.listdir(REPORTS_DIR), reverse=True):
            if fname.endswith(".json"):
                date_str = fname.replace("report_", "").replace(".json", "")
                reports.append(date_str)
        return reports
