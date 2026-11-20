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
    get_simulate_activity, set_simulate_activity,
    get_sound_muted, set_sound_muted,
    get_sound_volume, set_sound_volume,
    get_ai_autonomy, set_ai_autonomy,
    get_auto_start, set_auto_start,
)
from services.pet_memory import (
    remember, forget, get_memories, search_memories, get_memory_summary,
)

router = APIRouter(tags=["config"])

# Injected by main.py
pet_brain = None


# ── Config endpoints ──────────────────────────────────────────


class SaveConfigRequest(BaseModel):
    assistantName: str = "Pet"
    aiMode: str = "antigravity"
    deepseekToken: str = ""
    clickupToken: str = ""
    simulateActivity: bool = False
    soundMuted: bool = False
    soundVolume: float = 0.85
    aiAutonomy: bool = True
    autoStart: bool = False


@router.get("/config")
async def get_full_config():
    """Get all config values."""
    return {
        "assistantName": get_assistant_name(),
        "aiMode": get_ai_mode(),
        "deepseekToken": get_deepseek_token(),
        "clickupToken": get_clickup_token(),
        "simulateActivity": get_simulate_activity(),
        "soundMuted": get_sound_muted(),
        "soundVolume": get_sound_volume(),
        "aiAutonomy": get_ai_autonomy(),
        "autoStart": get_auto_start(),
    }


@router.post("/config")
async def save_full_config(req: SaveConfigRequest):
    """Save all config values at once."""
    set_assistant_name(req.assistantName)
    set_ai_mode(req.aiMode)
    set_simulate_activity(req.simulateActivity)
    set_sound_muted(req.soundMuted)
    set_sound_volume(req.soundVolume)
    set_ai_autonomy(req.aiAutonomy)
    set_auto_start(req.autoStart)
    if req.deepseekToken is not None:
        set_deepseek_token(req.deepseekToken.strip())

    if req.clickupToken and req.clickupToken.strip():
        cu_tok = req.clickupToken.strip()
        set_clickup_token(cu_tok)
        from integrations.clickup_config import save_token
        save_token(cu_tok)
        import integrations.clickup_routes as cu_routes
        if cu_routes.clickup_service is not None:
            try:
                cu_routes.clickup_service.connect(cu_tok)
            except Exception:
                pass
    elif req.clickupToken == "":
        set_clickup_token("")
        from integrations.clickup_config import delete_token
        delete_token()
        import integrations.clickup_routes as cu_routes
        if cu_routes.clickup_service is not None:
            try:
                cu_routes.clickup_service.disconnect()
            except Exception:
                pass

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
