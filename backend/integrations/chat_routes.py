"""
Chat history routes — API for persistent chat history.
"""

from datetime import date
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from integrations.chat_history import (
    save_message,
    get_history,
    get_today_sessions,
    clear_history,
)
from integrations.git_detector import GitDetector
from integrations.time_tracker import TimeTracker
from services.ai import chat as ai_chat

router = APIRouter(prefix="/chat", tags=["chat"])

# Injected by main.py
time_tracker = None


class ChatRequest(BaseModel):
    message: str
    session_id: str = "default"
    mode: str = "local"
    api_token: str = ""


class ChatResponse(BaseModel):
    response: str
    history_id: int


@router.post("/send")
async def chat_send(req: ChatRequest):
    """Send a message and get AI response. Saves both to history."""
    if not req.message.strip():
        raise HTTPException(400, "Mensaje vacío")

    from services.ai import is_ollama_available, is_deepseek_configured
    if req.mode == "local" and not is_ollama_available():
        return {"response": "⚠️ Ollama no está disponible. Usá mode=remote con un token de DeepSeek."}
    if req.mode == "remote" and not is_deepseek_configured(req.api_token):
        return {"response": "⚠️ Modo remoto requiere un token de DeepSeek. Configuralo en Ajustes."}

    # Save user message
    save_message(req.session_id, "user", req.message)

    # Build context from recent history
    recent = get_history(req.session_id, limit=20)
    messages = []
    for m in recent:
        messages.append({"role": m["role"], "content": m["content"]})

    # Add system context
    today_info = _get_today_context()
    system = f"""Eres {_get_assistant_name()}, una mascota virtual asistente de trabajo.
Hoy es {date.today().isoformat()}.
Contexto del día: {today_info}
Respondé frases cortas (máximo 20 palabras), amigables, en español.
Si preguntan por tareas, proyectos o tiempo, usá la información disponible."""

    messages.insert(0, {"role": "system", "content": system})

    try:
        result = ai_chat(
            messages=messages,
            mode=req.mode,
            api_token=req.api_token,
        )
        response = "😶"
        if result and result.get("message", {}).get("content"):
            response = result["message"]["content"].replace("</think>", "").replace("<think>", "").strip()[:150]

        # Save assistant response
        save_message(req.session_id, "assistant", response)
        return {"response": response}

    except Exception as e:
        response = f"Error: {e}"
        save_message(req.session_id, "assistant", response)
        raise HTTPException(500, str(e))


@router.get("/history")
async def chat_history(session_id: str = "default", limit: int = 50):
    """Get chat history for a session."""
    history = get_history(session_id, limit=limit)
    return {"count": len(history), "history": history}


@router.get("/sessions")
async def list_sessions():
    """List today's chat sessions."""
    return {"sessions": get_today_sessions()}


@router.post("/clear")
async def chat_clear(session_id: str | None = None):
    """Clear chat history (all or per session)."""
    deleted = clear_history(session_id)
    return {"deleted": deleted}


def _get_assistant_name() -> str:
    try:
        import json, os
        cfg_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "pet-config.json")
        if os.path.exists(cfg_path):
            cfg = json.load(open(cfg_path))
            return cfg.get("assistantName", "Pet")
    except:
        pass
    return "Pet"


def _get_today_context() -> str:
    """Build a summary of today's activity for AI context."""
    parts = []

    # Active tasks
    if time_tracker:
        try:
            projects = time_tracker.get_project_time_summary()
            if projects:
                parts.append(f"Proyectos: {', '.join(f'{k} ({round(v/60)}m)' for k, v in projects.items())}")
        except:
            pass

    # Git activity
    try:
        git = GitDetector()
        activity = git.get_git_summary()
        if activity:
            repos = [a["project"] for a in activity]
            parts.append(f"Git: {', '.join(repos)}")
    except:
        pass

    # Due tasks
    try:
        from integrations.clickup_db import get_cached_tasks
        tasks = get_cached_tasks(limit=100)
        pending = [t for t in tasks if (t.get("status") or "").lower() not in ("done", "closed")]
        due = [t for t in pending if t.get("due_date")]
        if due:
            parts.append(f"Tareas por vencer: {len(due)}")
    except:
        pass

    # Recent ClickUp mentions
    try:
        from integrations.clickup_mentions import get_mentions_tracker
        mentions = get_mentions_tracker().get_recent_mentions_summary(limit=3)
        if mentions:
            parts.append(f"Menciones recientes: {mentions}")
    except:
        pass

    return ". ".join(parts) if parts else "Sin datos registrados hoy"
