"""
AI Service — communicates with Ollama (local) or DeepSeek API (remote).
"""

import json
import urllib.request
from typing import Any

from services.logger import info, warning, error

OLLAMA_BASE = "http://localhost:11434"
DEEPSEEK_BASE = "https://api.deepseek.com/v1"
DEFAULT_MODEL = "deepseek-r1:8b"
DEEPSEEK_MODEL = "deepseek-chat"


# ── Health checks ──────────────────────────────────────────────

def is_ollama_available() -> bool:
    """Check if Ollama is running locally."""
    try:
        req = urllib.request.Request(f"{OLLAMA_BASE}/api/tags")
        with urllib.request.urlopen(req, timeout=2) as resp:
            return resp.status == 200
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
    Generate text using either local Ollama or remote DeepSeek API.
    """
    if mode == "remote" and api_token:
        return _generate_deepseek(prompt, system, api_token, timeout)
    return _generate_ollama(prompt, model, system, timeout)


def _generate_ollama(
    prompt: str,
    model: str = DEFAULT_MODEL,
    system: str = "",
    timeout: int = 120,
) -> str | None:
    """Generate via local Ollama."""
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
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode())
            return data.get("response", "").strip()
    except Exception as e:
        error(f"Ollama generate failed: {e}")
        return None


def _generate_deepseek(
    prompt: str,
    system: str = "",
    api_token: str = "",
    timeout: int = 120,
) -> str | None:
    """Generate via DeepSeek API (OpenAI-compatible)."""
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    payload = {
        "model": DEEPSEEK_MODEL,
        "messages": messages,
        "stream": False,
        "max_tokens": 1024,
        "temperature": 0.7,
    }

    try:
        req = urllib.request.Request(
            f"{DEEPSEEK_BASE}/chat/completions",
            data=json.dumps(payload).encode(),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_token}",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode())
            choices = data.get("choices", [])
            if choices:
                return choices[0].get("message", {}).get("content", "").strip()
            return None
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        error(f"DeepSeek API {e.code}: {body[:200]}")
        return None
    except Exception as e:
        error(f"DeepSeek generate failed: {e}")
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
    Chat completion. Supports Ollama and DeepSeek API.
    Returns dict with {message, content} or None.
    """
    if mode == "remote" and api_token:
        return _chat_deepseek(messages, api_token, timeout)
    return _chat_ollama(messages, model, timeout)


def _chat_ollama(
    messages: list[dict],
    model: str = DEFAULT_MODEL,
    timeout: int = 180,
) -> dict | None:
    """Chat via Ollama /api/chat."""
    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
    }
    try:
        req = urllib.request.Request(
            f"{OLLAMA_BASE}/api/chat",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode())
            msg = data.get("message", {})
            return {"message": {"content": msg.get("content", "").strip()}}
    except Exception as e:
        error(f"Ollama chat failed: {e}")
        return None


def _chat_deepseek(
    messages: list[dict],
    api_token: str = "",
    timeout: int = 180,
) -> dict | None:
    """Chat via DeepSeek API."""
    payload = {
        "model": DEEPSEEK_MODEL,
        "messages": messages,
        "stream": False,
        "max_tokens": 2048,
        "temperature": 0.7,
    }
    try:
        req = urllib.request.Request(
            f"{DEEPSEEK_BASE}/chat/completions",
            data=json.dumps(payload).encode(),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_token}",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode())
            choices = data.get("choices", [])
            if choices:
                return {"message": {"content": choices[0].get("message", {}).get("content", "").strip()}}
            return None
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        error(f"DeepSeek API {e.code}: {body[:200]}")
        return None
    except Exception as e:
        error(f"DeepSeek chat failed: {e}")
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
