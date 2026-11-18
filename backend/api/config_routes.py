"""
Config & Memory routes — API for persistent settings and pet memory.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from services.config_store import (
    get_all_config, get_config, set_config, delete_config,
    get_assistant_name, set_assistant_name,
    get_clickup_token, set_clickup_token,
    get_deepseek_token, set_deepseek_token,
    get_ai_mode, set_ai_mode,
)
from services.pet_memory import (
    remember, forget, get_memories, search_memories, get_memory_summary,
)

router = APIRouter(tags=["config"])


# ── Config endpoints ──────────────────────────────────────────


class SaveConfigRequest(BaseModel):
    assistantName: str = "Pet"
    aiMode: str = "local"
    deepseekToken: str = ""
    clickupToken: str = ""


@router.get("/config")
async def get_full_config():
    """Get all config values."""
    return {
        "assistantName": get_assistant_name(),
        "aiMode": get_ai_mode(),
        "deepseekToken": get_deepseek_token(),
        "clickupToken": get_clickup_token(),
    }


@router.post("/config")
async def save_full_config(req: SaveConfigRequest):
    """Save all config values at once."""
    set_assistant_name(req.assistantName)
    set_ai_mode(req.aiMode)
    if req.deepseekToken:
        set_deepseek_token(req.deepseekToken)
    if req.clickupToken:
        set_clickup_token(req.clickupToken)
        # Also save to clickup_config for backward compat
        from integrations.clickup_config import save_token
        save_token(req.clickupToken)
    return {"saved": True}


@router.get("/config/{key}")
async def get_config_value(key: str):
    """Get a single config value."""
    value = get_config(key)
    return {"key": key, "value": value}


@router.put("/config/{key}")
async def set_config_value(key: str, value: str):
    """Set a single config value."""
    set_config(key, value)
    return {"key": key, "value": value}


# ── Memory endpoints ──────────────────────────────────────────


class RememberRequest(BaseModel):
    content: str
    category: str = "general"


@router.post("/memory/remember")
async def api_remember(req: RememberRequest):
    """Save something to pet memory."""
    if not req.content.strip():
        raise HTTPException(400, "Contenido vacío")
    mid = remember(req.content, req.category)
    return {"id": mid, "message": f"Guardado: {req.content[:50]}"}


@router.get("/memory")
async def api_get_memories(category: str | None = None, limit: int = 50):
    """Get all active memories."""
    memories = get_memories(category=category, limit=limit)
    return {"count": len(memories), "memories": memories}


@router.get("/memory/search")
async def api_search_memories(q: str, limit: int = 10):
    """Search memories by content."""
    results = search_memories(q, limit=limit)
    return {"count": len(results), "results": results}


@router.delete("/memory/{memory_id}")
async def api_forget(memory_id: int):
    """Forget (soft delete) a memory."""
    forget(memory_id)
    return {"forgotten": True}
