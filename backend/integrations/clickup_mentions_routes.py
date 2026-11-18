"""
ClickUp Mentions routes — endpoints for mention/comment checking.
"""

from fastapi import APIRouter, HTTPException
from integrations.clickup_mentions import get_mentions_tracker
from services.logger import info

router = APIRouter(prefix="/clickup/mentions", tags=["clickup"])


@router.get("/check")
async def check_mentions():
    """
    Check for new comments/mentions on ClickUp tasks.
    Returns any new mentions found since last check.
    """
    try:
        mentions = get_mentions_tracker().check_new_mentions()
        return {
            "new_mentions": mentions,
            "count": len(mentions),
        }
    except Exception as e:
        raise HTTPException(500, f"Error checking mentions: {e}")


@router.get("/summary")
async def mentions_summary():
    """Get a summary of recent mentions for AI context."""
    try:
        summary = get_mentions_tracker().get_recent_mentions_summary()
        return {
            "summary": summary,
            "has_mentions": bool(summary),
        }
    except Exception as e:
        raise HTTPException(500, f"Error getting mentions summary: {e}")
