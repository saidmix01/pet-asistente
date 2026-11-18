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
pet_brain = None


class ChatRequest(BaseModel):
    message: str
    session_id: str = "default"
    mode: str = "antigravity"
    api_token: str = ""
    assistant_name: str = "Pet"


class ChatResponse(BaseModel):
    response: str
    history_id: int


@router.post("/send")
def chat_send(req: ChatRequest):
    """Send a message and get AI response. Saves both to history."""
    if not req.message.strip():
        raise HTTPException(400, "Mensaje vacío")

    from services.ai import is_antigravity_available, is_ollama_available, is_deepseek_configured
    if req.mode == "antigravity" and not is_antigravity_available():
        return {"response": "⚠️ Antigravity CLI (`agy`) no encontrado. Instalalo con: curl -fsSL https://antigravity.google/cli/install.sh | bash (Linux) o irm https://antigravity.google/cli/install.ps1 | iex (Windows) y ejecutá `agy` para iniciar sesión."}
    if req.mode == "local" and not is_ollama_available():
        return {"response": "⚠️ Ollama no está disponible. Probá con Antigravity CLI o DeepSeek en Ajustes."}
    if req.mode == "remote" and not is_deepseek_configured(req.api_token):
        return {"response": "⚠️ Modo remoto requiere un token de DeepSeek. Configuralo en Ajustes."}

    # Save user message
    save_message(req.session_id, "user", req.message)

    # Check if user wants to save something to memory
    _check_memory_request(req.message)

    # Build context from recent history
    recent = get_history(req.session_id, limit=20)
    messages = []
    for m in recent:
        messages.append({"role": m["role"], "content": m["content"]})

    # Add system context
    today_info = _get_today_context()
    memory_info = _get_memory_context()
    assistant_name = req.assistant_name or _get_assistant_name()
    system = f"""Eres {assistant_name}, un leal pug pixel-art y asistente de trabajo virtual que vive en el escritorio del usuario.
Hoy es {date.today().isoformat()}.
Contexto del día:
{today_info}
{memory_info}
Respondé de forma concisa y amigable, en español (máximo 80 palabras).
Si el usuario te pide una orden física (ej: salta, sube un escalón, baja al suelo, trepa a mi ventana, busca la pelota, come un snack, ven, siéntate, duérmete, muévete, olfatea, camina) o celebras con él, puedes incluir al final de tu respuesta una etiqueta con la acción física que realizarás:
- Para saltar y quedar sobre un escalón/plataforma elevada: usa "action": "jump_up" (o "jump")
- Para descender un escalón: usa "action": "jump_down"
- Para bajar todo de vuelta al suelo: usa "action": "reset_step"
- Para trepar sobre la ventana activa del usuario: usa "action": "climb_window"
- Para jugar a traer la pelota: usa "action": "fetch_ball"
- Para comer un snack o premio: usa "action": "feed_snack"
[ACTION: {{"action": "jump_up" | "jump_down" | "reset_step" | "climb_window" | "fetch_ball" | "feed_snack" | "jump" | "sit" | "walk" | "run" | "sniff" | "sniffwalk" | "idle", "direction": "left" | "right" | "keep", "move_to": "left" | "center" | "right" | null, "sound": "none" | "ladrido" | "ronquido", "mood": "playful" | "focused" | "happy" | "sleepy" | "calm"}}]"""

    messages.insert(0, {"role": "system", "content": system})

    try:
        result = ai_chat(
            messages=messages,
            mode=req.mode,
            api_token=req.api_token,
        )
        response = "😶"
        action_dispatched = None
        if result and result.get("message", {}).get("content"):
            raw_text = result["message"]["content"].replace("</think>", "").replace("<think>", "").strip()
            from core.pet_brain import extract_chat_action
            clean_text, action = extract_chat_action(raw_text)
            response = clean_text[:500] if clean_text else "🐾"
            if action and pet_brain:
                try:
                    action_dispatched = pet_brain.dispatch_action(action)
                except Exception:
                    pass

        # Save assistant response
        save_message(req.session_id, "assistant", response)
        return {"response": response, "action": action_dispatched}

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
        from services.config_store import get_assistant_name
        return get_assistant_name()
    except:
        return "Pet"


def _get_memory_context() -> str:
    """Get pet memory summary for AI context."""
    try:
        from services.pet_memory import get_memory_summary
        summary = get_memory_summary(limit=10)
        return summary if summary else ""
    except:
        return ""


def _check_memory_request(message: str) -> None:
    """Detect if user wants the pet to remember something and save it."""
    msg = message.lower().strip()
    triggers = ["recuerda que", "recordá que", "acuerdate que", "acordate que",
                "guarda esto", "guardá esto", "no olvides que", "anota que", "anotá que"]
    for trigger in triggers:
        if trigger in msg:
            # Extract what to remember (everything after the trigger)
            idx = msg.index(trigger) + len(trigger)
            content = message[idx:].strip()
            if content:
                from services.pet_memory import remember
                remember(content)
            break


def _get_today_context() -> str:
    """Build a detailed summary of today's activity for AI context."""
    parts = []

    # Active tasks with details
    try:
        from integrations.clickup_db import get_cached_tasks
        tasks = get_cached_tasks(limit=100)
        pending = [t for t in tasks if (t.get("status") or "").lower() not in ("done", "closed", "completed")]

        if pending:
            # Group by status
            in_progress = [t for t in pending if (t.get("status") or "").lower() in ("in progress", "doing", "in review")]
            todo = [t for t in pending if (t.get("status") or "").lower() in ("to do", "open", "todo")]
            overdue = []

            from datetime import datetime, timezone
            now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
            for t in pending:
                due = t.get("due_date")
                if due:
                    try:
                        if int(due) < now_ms:
                            overdue.append(t)
                    except:
                        pass

            if in_progress:
                task_list = ", ".join(f'"{t["name"]}" ({t.get("project_name", "")})'  for t in in_progress[:5])
                parts.append(f"En progreso: {task_list}")
            if overdue:
                task_list = ", ".join(f'"{t["name"]}"' for t in overdue[:3])
                parts.append(f"VENCIDAS: {task_list}")
            if todo:
                parts.append(f"Pendientes: {len(todo)} tareas")
    except:
        pass

    # Time tracking
    if time_tracker:
        try:
            projects = time_tracker.get_project_time_summary()
            if projects:
                parts.append(f"Tiempo hoy: {', '.join(f'{k} ({round(v/60)}m)' for k, v in projects.items())}")
        except:
            pass

    # Git activity
    try:
        git = GitDetector()
        activity = git.get_git_summary()
        if activity:
            repos = [a["project"] for a in activity[:3]]
            parts.append(f"Git: {', '.join(repos)}")
    except:
        pass

    # Recent ClickUp mentions
    try:
        from integrations.clickup_mentions import get_mentions_tracker
        mentions = get_mentions_tracker().get_recent_mentions_summary(limit=3)
        if mentions:
            parts.append(f"Menciones recientes:\n{mentions}")
    except:
        pass

    return "\n".join(parts) if parts else "Sin datos registrados hoy"
