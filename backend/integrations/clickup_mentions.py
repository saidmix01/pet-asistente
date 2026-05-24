"""
ClickUp Mentions — tracks new comments and mentions on tasks.
"""

import json
import os
import time
from datetime import datetime, timezone
from typing import Any

from integrations.clickup_client import ClickUpClient
from integrations.clickup_config import load_token
from integrations.clickup_db import get_cached_tasks
from services.logger import info, warning, error

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
STATE_FILE = os.path.join(DATA_DIR, "mentions_state.json")


def _load_state() -> dict:
    try:
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE) as f:
                return json.load(f)
    except Exception:
        pass
    return {"last_checked_ts": 0, "notified_ids": []}


def _save_state(state: dict) -> None:
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


class MentionTracker:
    """Tracks new comments and mentions across ClickUp tasks."""

    def __init__(self) -> None:
        self._client: ClickUpClient | None = None
        self._state = _load_state()

    def _ensure_client(self) -> ClickUpClient:
        if self._client is not None:
            return self._client
        token = load_token()
        if not token:
            raise RuntimeError("ClickUp not configured")
        self._client = ClickUpClient(token)
        return self._client

    def check_new_mentions(self) -> list[dict]:
        """
        Check all cached tasks for new comments.
        Returns list of new mention events.
        """
        token = load_token()
        if not token:
            return []

        try:
            client = self._ensure_client()
            tasks = get_cached_tasks(limit=100)
            last_checked = self._state.get("last_checked_ts", 0)
            new_mentions = []
            checked_count = 0

            for task in tasks:
                task_id = task.get("id")
                if not task_id:
                    continue

                try:
                    comments = client.get_task_comments(task_id)
                    checked_count += 1
                except Exception:
                    continue

                for comment in comments:
                    created = int(comment.get("date", 0))
                    resolved = comment.get("resolved", False)

                    # Only new, unresolved comments
                    if created > last_checked and not resolved:
                        comment_id = comment.get("id", "")
                        if comment_id not in self._state.get("notified_ids", []):
                            new_mentions.append({
                                "id": comment_id,
                                "task_id": task_id,
                                "task_name": task.get("name", "Sin nombre"),
                                "comment_text": comment.get("comment_text", ""),
                                "created": created,
                                "author": comment.get("user", {}).get("username", "Alguien"),
                            })

            # Update state
            self._state["last_checked_ts"] = int(time.time() * 1000)
            self._state["notified_ids"] = (
                self._state.get("notified_ids", []) +
                [m["id"] for m in new_mentions]
            )
            # Keep only last 200 notified IDs to avoid unbounded growth
            self._state["notified_ids"] = self._state["notified_ids"][-200:]
            _save_state(self._state)

            if new_mentions:
                info(f"MentionTracker: {len(new_mentions)} new mentions found (checked {checked_count} tasks)")

            return new_mentions

        except RuntimeError:
            return []
        except Exception as e:
            error(f"MentionTracker error: {e}")
            return []

    def get_recent_mentions_summary(self, limit: int = 5) -> str:
        """Get a text summary of recent mentions for AI context."""
        notified = self._state.get("notified_ids", [])
        if not notified:
            return ""

        # Re-check the most recent mentions from state
        token = load_token()
        if not token:
            return ""

        try:
            client = self._ensure_client()
            tasks = get_cached_tasks(limit=50)
            mentions_text = []

            for task in tasks:
                task_id = task.get("id")
                if not task_id:
                    continue
                try:
                    comments = client.get_task_comments(task_id)
                except Exception:
                    continue

                for comment in comments:
                    cid = comment.get("id", "")
                    if cid in notified:
                        mentions_text.append(
                            f"📬 {comment.get('user', {}).get('username', 'Alguien')} "
                            f"en \"{task.get('name', 'tarea')}\": "
                            f"\"{comment.get('comment_text', '')[:100]}\""
                        )

            mentions_text = mentions_text[:limit]
            if mentions_text:
                return "\n".join(mentions_text)
            return ""

        except Exception:
            return ""


# ── Singleton instance ────────────────────────────────────

_mentions_tracker: MentionTracker | None = None


def get_mentions_tracker() -> MentionTracker:
    global _mentions_tracker
    if _mentions_tracker is None:
        _mentions_tracker = MentionTracker()
    return _mentions_tracker
