"""
Auto Report — generates and saves the daily report at 4pm.
Combines: TaskTracker data + Git activity + Daily Log entries.
"""

import os
import json
import time
import threading
from datetime import datetime, timezone, date

from integrations.daily_log import get_logs_by_date, generate_report
from integrations.git_detector import GitDetector
from integrations.task_tracker import TaskTracker
from services.logger import info, warning, error

REPORTS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "daily_reports")


class AutoReport:
    """
    Generates and saves the daily report automatically at 4pm local time.
    Also available on demand via API.
    """

    def __init__(self, task_tracker: TaskTracker | None = None) -> None:
        self._task_tracker = task_tracker
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

        # 4. Generate text report
        text_report = generate_report(today)

        # 5. Try AI enhancement
        from services.ai import is_available, enhance_daily_report

        ai_enhanced = None
        if is_available():
            try:
                ai_data = {
                    "date": today,
                    "logs": logs,
                    "git_activity": git_activity,
                    "time_summary": {},
                    "raw_text": text_report,
                }
                ai_enhanced = enhance_daily_report(ai_data)
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

        with open(filepath, "w") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)

        info(f"Daily report saved: {filepath}")

        # Also save a plaintext version
        txt_path = os.path.join(REPORTS_DIR, f"report_{today}.txt")
        with open(txt_path, "w") as f:
            f.write(text_report)

        return filepath

    # ── Load saved reports ────────────────────────────────────────────

    def get_report(self, report_date: str | None = None) -> dict | None:
        """Load a previously saved report."""
        target = report_date or date.today().isoformat()
        filepath = os.path.join(REPORTS_DIR, f"report_{target}.json")
        if os.path.exists(filepath):
            with open(filepath) as f:
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
