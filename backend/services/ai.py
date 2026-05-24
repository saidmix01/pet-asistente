"""
AI Service — communicates with the AI Gateway on the server.
The gateway handles Ollama (local) + DeepSeek (remote) routing.
"""

import json
import urllib.request
from typing import Any

from services.logger import info, warning, error

GATEWAY_BASE = "http://192.168.1.6:8888"
DEFAULT_MODEL = "qwen2:0.5b"


# ── Health checks ──────────────────────────────────────────────

def is_ollama_available() -> bool:
    """Check if Ollama is running via the gateway."""
    try:
        req = urllib.request.Request(f"{GATEWAY_BASE}/health")
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read().decode())
            return data.get("ollama_available", False)
    except Exception:
        return False


def is_deepseek_configured(token: str = "") -> bool:
    return len(token) > 10


# ── Generate ──────────────────────────────────────────────────

def generate(
    prompt: str,
    model: str = DEFAULT_MODEL,
    system: str = "",
    mode: str = "local",
    api_token: str = "",
    timeout: int = 120,
) -> str | None:
    """
    Generate text via the AI Gateway.
    Supports mode="local" (Ollama) and mode="remote" (DeepSeek).
    """
    payload = {
        "model": model,
        "prompt": prompt,
        "system": system,
        "mode": mode,
        "api_token": api_token,
    }

    try:
        req = urllib.request.Request(
            f"{GATEWAY_BASE}/generate",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode())
            return data.get("response", "").strip()
    except urllib.error.HTTPError as e:
        body = e.read().decode()[:200]
        error(f"Gateway generate error {e.code}: {body}")
        return None
    except Exception as e:
        error(f"Gateway generate failed: {e}")
        return None


# ── Chat (for the mascota chat window) ────────────────────────

def chat(
    messages: list[dict],
    model: str = DEFAULT_MODEL,
    mode: str = "local",
    api_token: str = "",
    timeout: int = 180,
) -> dict | None:
    """
    Chat completion via the AI Gateway (OpenAI-compatible).
    Returns dict with {message, content} or None.
    """
    payload = {
        "model": model,
        "messages": messages,
        "mode": mode,
        "api_token": api_token,
    }

    try:
        req = urllib.request.Request(
            f"{GATEWAY_BASE}/v1/chat/completions",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode())
            choices = data.get("choices", [])
            if choices:
                content = choices[0].get("message", {}).get("content", "").strip()
                return {"message": {"content": content}}
            return None
    except urllib.error.HTTPError as e:
        body = e.read().decode()[:200]
        error(f"Gateway chat error {e.code}: {body}")
        return None
    except Exception as e:
        error(f"Gateway chat failed: {e}")
        return None


# ── Report enhancers ──────────────────────────────────────────

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


def enhance_daily_report(
    report_data: dict,
    mode: str = "local",
    api_token: str = "",
) -> str | None:
    """Take raw daily report data and return a clean AI-generated summary."""
    prompt_data = {
        "date": report_data.get("date", ""),
        "logs": report_data.get("logs", []),
        "git_activity": report_data.get("git_activity", []),
        "time_summary": report_data.get("time_summary", {}),
    }

    prompt = f"""Genera un reporte diario limpio a partir de estos datos:

{json.dumps(prompt_data, indent=2, ensure_ascii=False)}

Sigue exactamente el formato instruido y no agregues nada extra."""

    return generate(prompt, system=DAILY_REPORT_SYSTEM, mode=mode, api_token=api_token)


QUICK_SUMMARY_SYSTEM = """Resumís datos de trabajo en 3-4 líneas claras.
Solo hechos, sin relleno."""


def quick_summary(
    text: str,
    mode: str = "local",
    api_token: str = "",
) -> str | None:
    """Generate a one-paragraph quick summary."""
    prompt = f"Resumí este reporte en 3 líneas:\n\n{text[:2000]}"
    return generate(prompt, system=QUICK_SUMMARY_SYSTEM, mode=mode, api_token=api_token)
