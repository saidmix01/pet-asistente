"""
AI Report routes — endpoints to generate AI-enhanced reports via Ollama.
"""

import json
from datetime import date

import urllib.request
from fastapi import APIRouter, HTTPException, Query

from integrations.daily_log import get_logs_by_date, generate_report as generate_text_report
from integrations.git_detector import GitDetector
from integrations.time_tracker import TimeTracker
from services.ai import is_available, list_models, enhance_daily_report, quick_summary

router = APIRouter(prefix="/ai", tags=["ai"])

# Injected by main.py
time_tracker = None


@router.get("/status")
async def ai_status():
    """Check if Ollama is available and list models."""
    available = is_available()
    models = list_models() if available else []
    return {
        "available": available,
        "models": models,
    }


@router.get("/report")
async def ai_enhanced_report(date_str: str | None = Query(None, alias="date")):
    """
    Generate an AI-enhanced daily report.
    Combines: daily logs + git activity + time tracking
    Then processes through Ollama for a clean format.
    """
    if not is_available():
        raise HTTPException(503, "Ollama no está disponible. Instalá Ollama y descargá deepseek-r1:8b")

    today = date.today().isoformat()
    report_date = date_str or today

    # 1. Get raw data
    logs = get_logs_by_date(report_date)
    text_report = generate_text_report(report_date)

    # 2. Git activity
    try:
        git = GitDetector()
        git_activity = git.get_git_summary()
    except Exception:
        git_activity = []

    # 3. Time tracking
    time_data = {}
    if time_tracker:
        time_data = time_tracker.get_project_time_summary()
        entries = time_tracker.get_today_entries()

    # 4. Build data for AI
    report_data = {
        "date": report_date,
        "logs": logs,
        "git_activity": git_activity,
        "time_summary": time_data,
        "raw_text": text_report,
    }

    # 5. Process with Ollama
    enhanced = enhance_daily_report(report_data)

    return {
        "date": report_date,
        "enhanced": enhanced,
        "model": "deepseek-r1:8b",
    }


@router.post("/chat")
async def pet_chat(message: dict):
    """Proxy para que el pet pueda chatear con Ollama sin CORS."""
    if not is_available():
        raise HTTPException(503, "Ollama no está disponible")
    user_msg = message.get("message", "").strip()
    if not user_msg:
        raise HTTPException(400, "Mensaje vacío")
    try:
        payload = {
            "model": "deepseek-r1:8b",
            "messages": [
                {"role": "system", "content": "Eres una mascota virtual graciosa, amigable. Respondes con frases cortas de máximo 15 palabras. Hablas en español."},
                {"role": "user", "content": user_msg},
            ],
            "stream": False,
            "options": {"num_predict": 50},
        }
        req = urllib.request.Request(
            "http://localhost:11434/api/chat",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=180) as resp:
            data = json.loads(resp.read().decode())
            text = (data.get("message", {}) or {}).get("content", "").strip()
            clean = text.replace("</think>", "").replace("<think>", "").strip()[:100]
            return {"response": clean}
    except Exception as e:
        raise HTTPException(500, f"Chat failed: {e}")


@router.get("/summarize")
async def ai_summarize(text: str = Query(""), date_str: str | None = Query(None, alias="date")):
    """Get a quick AI summary of today's report."""
    if not is_available():
        raise HTTPException(503, "Ollama no está disponible")

    if not text:
        today = date.today().isoformat()
        text = generate_text_report(date_str or today)

    summary = quick_summary(text[:3000])
    return {"summary": summary}
