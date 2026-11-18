"""
AI Report routes — endpoints to generate AI-enhanced reports via Ollama or DeepSeek.
"""

import json
from datetime import date

import urllib.request
from fastapi import APIRouter, HTTPException, Query

from integrations.daily_log import get_logs_by_date, generate_report as generate_text_report
from integrations.git_detector import GitDetector
from integrations.time_tracker import TimeTracker
from services.ai import (
    find_antigravity_cli,
    is_antigravity_available,
    is_ollama_available,
    is_deepseek_configured,
    enhance_daily_report,
    quick_summary,
    chat as ai_chat,
    generate as ai_generate,
)

router = APIRouter(prefix="/ai", tags=["ai"])

# Injected by main.py
time_tracker = None
pet_brain = None


@router.get("/status")
def ai_status():
    """Check available AI modes."""
    agy_path = find_antigravity_cli()
    antigravity = agy_path is not None
    ollama = is_ollama_available()
    recommended = "antigravity" if antigravity else ("local" if ollama else "remote")
    return {
        "antigravity_available": antigravity,
        "antigravity_path": agy_path,
        "ollama_available": ollama,
        "mode": recommended,
    }


@router.get("/report")
def ai_enhanced_report(
    date_str: str | None = Query(None, alias="date"),
    mode: str = Query("antigravity"),
    api_token: str = Query(""),
):
    """
    Generate an AI-enhanced daily report.
    Supports: mode=antigravity (agy CLI), mode=local (Ollama), or mode=remote (DeepSeek).
    """
    if mode == "antigravity" and not is_antigravity_available():
        raise HTTPException(503, "Antigravity CLI (`agy`) no está instalado en PATH.")
    if mode == "local" and not is_ollama_available():
        raise HTTPException(503, "Ollama no disponible. Usá mode=antigravity o mode=remote con DeepSeek.")
    if mode == "remote" and not is_deepseek_configured(api_token):
        raise HTTPException(400, "Token de DeepSeek requerido para modo remoto")

    today = date.today().isoformat()
    report_date = date_str or today

    logs = get_logs_by_date(report_date)
    text_report = generate_text_report(report_date)

    try:
        git = GitDetector()
        git_activity = git.get_git_summary()
    except Exception:
        git_activity = []

    time_data = {}
    if time_tracker:
        time_data = time_tracker.get_project_time_summary()

    report_data = {
        "date": report_date,
        "logs": logs,
        "git_activity": git_activity,
        "time_summary": time_data,
        "raw_text": text_report,
    }

    enhanced = enhance_daily_report(report_data, mode=mode, api_token=api_token)

    model_used = (
        "antigravity-cli" if mode == "antigravity"
        else ("qwen2:0.5b" if mode == "local" else "deepseek-chat")
    )
    return {
        "date": report_date,
        "enhanced": enhanced,
        "mode": mode,
        "model": model_used,
    }


@router.post("/chat")
def pet_chat(message: dict):
    """Proxy para que el pet pueda chatear con Antigravity CLI, Ollama o DeepSeek."""
    user_msg = message.get("message", "").strip()
    mode = message.get("mode", "antigravity")
    api_token = message.get("api_token", "")

    if not user_msg:
        raise HTTPException(400, "Mensaje vacío")

    if mode == "antigravity" and not is_antigravity_available():
        raise HTTPException(503, "Antigravity CLI (`agy`) no disponible")
    if mode == "local" and not is_ollama_available():
        raise HTTPException(503, "Ollama no disponible")

    system_prompt = "Eres una mascota virtual graciosa, amigable. Respondes con frases cortas de máximo 15 palabras. Hablas en español."

    try:
        result = ai_chat(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_msg},
            ],
            mode=mode,
            api_token=api_token,
        )
        if result and result.get("message", {}).get("content"):
            text = result["message"]["content"]
            clean = text.replace("</think>", "").replace("<think>", "").strip()[:100]
            return {"response": clean}
        raise HTTPException(500, "No response from AI")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Chat failed: {e}")


@router.post("/generate")
def pet_generate(body: dict):
    """Generic generation endpoint."""
    prompt = body.get("prompt", "").strip()
    system = body.get("system", "")
    mode = body.get("mode", "antigravity")
    api_token = body.get("api_token", "")

    if not prompt:
        raise HTTPException(400, "Prompt vacío")

    result = ai_generate(prompt, system=system, mode=mode, api_token=api_token)
    if not result:
        raise HTTPException(500, "No response from AI")
    return {"response": result}


@router.get("/summarize")
def ai_summarize(
    text: str = Query(""),
    date_str: str | None = Query(None, alias="date"),
    mode: str = Query("antigravity"),
    api_token: str = Query(""),
):
    """Get a quick AI summary of today's report."""
    if not text:
        today = date.today().isoformat()
        text = generate_text_report(date_str or today)

    summary = quick_summary(text[:3000], mode=mode, api_token=api_token)
    return {"summary": summary}


# ── AI Pet Brain endpoints ────────────────────────────────────


@router.get("/pet/status")
def pet_brain_status():
    """Return current AI Pet Brain status (mood, last action, autonomy)."""
    if pet_brain is None:
        return {"autonomy_enabled": False, "ai_ready": False, "mood": "calm", "last_action": None}
    return pet_brain.get_status()


@router.post("/pet/think")
def pet_brain_think():
    """Ask the AI to decide a new movement/behavior for the pet right now."""
    if pet_brain is None:
        raise HTTPException(500, "PetBrain not initialized")
    action = pet_brain.decide_now(trigger="manual")
    if not action:
        raise HTTPException(503, "IA no disponible o ocupada pensando")
    return {"ok": True, "action": action}


@router.post("/pet/command")
def pet_brain_command(body: dict):
    """Give the pet a natural-language physical command handled by the AI."""
    if pet_brain is None:
        raise HTTPException(500, "PetBrain not initialized")
    cmd = str(body.get("command", "")).strip()
    if not cmd:
        raise HTTPException(400, "Comando vacío")
    action = pet_brain.decide_now(trigger="user_command", user_hint=cmd)
    if not action:
        raise HTTPException(503, "IA no disponible o ocupada pensando")
    return {"ok": True, "action": action}


@router.post("/pet/action")
def pet_brain_direct_action(body: dict):
    """Dispatch a structured pet action immediately."""
    if pet_brain is None:
        raise HTTPException(500, "PetBrain not initialized")
    action = pet_brain.dispatch_action(body or {})
    return {"ok": True, "action": action}
