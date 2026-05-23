"""
AI Service — communicates with local Ollama to process and enhance reports.
"""

import json
import urllib.request
from typing import Any

from services.logger import info, warning, error

OLLAMA_BASE = "http://localhost:11434"
DEFAULT_MODEL = "deepseek-r1:1.5b"


def is_available() -> bool:
    """Check if Ollama is running locally."""
    try:
        req = urllib.request.Request(f"{OLLAMA_BASE}/api/tags")
        with urllib.request.urlopen(req, timeout=2) as resp:
            return resp.status == 200
    except Exception:
        return False


def list_models() -> list[str]:
    """Return list of available models."""
    try:
        req = urllib.request.Request(f"{OLLAMA_BASE}/api/tags")
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read().decode())
            return [m["name"] for m in data.get("models", [])]
    except Exception as e:
        warning(f"Ollama list models failed: {e}")
        return []


def generate(prompt: str, model: str = DEFAULT_MODEL, system: str = "") -> str | None:
    """
    Send a prompt to Ollama and return the response.
    Uses the /api/generate endpoint (non-streaming).
    """
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
    }
    if system:
        payload["system"] = system

    try:
        req = urllib.request.Request(
            f"{OLLAMA_BASE}/api/generate",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read().decode())
            return data.get("response", "").strip()
    except Exception as e:
        error(f"Ollama generate failed: {e}")
        return None


# ── Report enhancers ──────────────────────────────────────────────────


DAILY_REPORT_SYSTEM = """Eres un asistente que genera reportes diarios de trabajo limpios y profesionales.
Recibes datos en JSON y debes convertirlos en un resumen claro.

FORMATO DE SALIDA:
📋 Reporte Diario — [fecha]

⏱️ Tiempo por Actividad
- Coding: Xh Xm
- Browsing: Xh Xm
- Reading: Xh Xm
- Otros: Xh Xm

📌 Tareas Trabajadas
- [Proyecto] Tarea: X% — Xh Xm
  • Notas breves del trabajo realizado

🐙 Git
- [proyecto] - rama (X commits)

📊 Resumen
- Total tiempo productivo: Xh Xm
- Tareas completadas: X
- Proyectos: X

IMPORTANTE: Solo datos, sin opiniones ni sugerencias. Máximo 30 líneas."""


def enhance_daily_report(report_data: dict) -> str | None:
    """
    Take raw daily report data and return a clean AI-generated summary.
    """
    # Build a compact JSON for the prompt
    prompt_data = {
        "date": report_data.get("date", ""),
        "logs": report_data.get("logs", []),
        "git_activity": report_data.get("git_activity", []),
        "time_summary": report_data.get("time_summary", {}),
    }

    prompt = f"""Genera un reporte diario limpio a partir de estos datos:

{json.dumps(prompt_data, indent=2, ensure_ascii=False)}

Sigue exactamente el formato instruido y no agregues nada extra."""

    result = generate(prompt, system=DAILY_REPORT_SYSTEM)
    return result


QUICK_SUMMARY_SYSTEM = """Resumís datos de trabajo en 3-4 líneas claras.
Solo hechos, sin relleno."""


def quick_summary(text: str) -> str | None:
    """Generate a one-paragraph quick summary."""
    prompt = f"Resumí este reporte en 3 líneas:\n\n{text[:2000]}"
    return generate(prompt, system=QUICK_SUMMARY_SYSTEM)
