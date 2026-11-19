"""
AI Service — communicates with Antigravity CLI (`agy`), Ollama (local), or DeepSeek API (remote).
"""

import json
import os
import re
import shutil
import ssl
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from typing import Any

from services.logger import info, warning, error


def _ssl_context() -> ssl.SSLContext:
    """Create SSL context compatible with Windows and Linux (dev & frozen)."""
    ctx = ssl.create_default_context()
    if getattr(sys, 'frozen', False) and os.name == 'nt':
        return ctx
    try:
        import certifi
        ctx.load_verify_locations(certifi.where())
    except Exception:
        pass
    return ctx


OLLAMA_BASE = "http://localhost:11434"
DEEPSEEK_BASE = "https://api.deepseek.com/v1"
DEFAULT_MODEL = "qwen2:0.5b"
DEEPSEEK_MODEL = "deepseek-chat"
ANSI_ESCAPE_RE = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")


# ── Health checks ──────────────────────────────────────────────

def find_antigravity_cli() -> str | None:
    """Locate the Antigravity CLI (`agy`) executable on Windows, Linux, or macOS."""
    for env_var in ("ANTIGRAVITY_CLI", "AGY_BIN"):
        custom = os.environ.get(env_var, "").strip()
        if custom and os.path.isfile(custom):
            return custom

    found = shutil.which("agy")
    if found:
        return found

    home = os.path.expanduser("~")
    if os.name == "nt":
        local_app_data = os.environ.get("LOCALAPPDATA", "")
        candidates = [
            os.path.join(local_app_data, "agy", "bin", "agy.exe"),
            os.path.join(local_app_data, "agy", "bin", "agy.cmd"),
            os.path.join(local_app_data, "Antigravity", "bin", "agy.exe"),
            os.path.join(local_app_data, "Antigravity", "bin", "agy.cmd"),
            os.path.join(home, ".antigravity", "bin", "agy.exe"),
            os.path.join(home, ".antigravity", "bin", "agy.cmd"),
            os.path.join(home, ".local", "bin", "agy.exe"),
            os.path.join(home, ".local", "bin", "agy.cmd"),
        ]
    else:
        candidates = [
            os.path.join(home, ".local", "bin", "agy"),
            os.path.join(home, ".antigravity", "bin", "agy"),
            os.path.join(home, ".gemini", "antigravity", "bin", "agy"),
            "/usr/local/bin/agy",
            "/usr/bin/agy",
        ]

    for path in candidates:
        if path and os.path.isfile(path):
            return path
    return None


def is_antigravity_available() -> bool:
    """Check if Antigravity CLI (`agy`) is installed and discoverable."""
    return find_antigravity_cli() is not None


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


# ── Antigravity CLI (`agy`) helper ────────────────────────────

def _run_antigravity_cli(prompt: str, timeout: int = 120) -> str | None:
    """Invoke `agy -p <prompt>` in headless mode and return stdout text."""
    agy_bin = find_antigravity_cli()
    if not agy_bin:
        warning("Antigravity CLI (`agy`) not found in PATH")
        return None

    kwargs: dict[str, Any] = {
        "capture_output": True,
        "text": True,
        "encoding": "utf-8",
        "errors": "replace",
        "timeout": timeout,
        "cwd": tempfile.gettempdir(),
    }
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW

    cmd = [
        agy_bin,
        "-p",
        prompt,
        "--disable-slash-commands",
        "--effort",
        "low",
        "--print-timeout",
        f"{max(10, int(timeout))}s",
    ]

    try:
        res = subprocess.run(cmd, **kwargs)
        stdout = ANSI_ESCAPE_RE.sub("", res.stdout or "").strip()
        if res.returncode == 0 and stdout:
            return stdout
        stderr = ANSI_ESCAPE_RE.sub("", res.stderr or "").strip()
        error(f"Antigravity CLI exited with {res.returncode}: {stderr[:300] or stdout[:300]}")
        return stdout or None
    except subprocess.TimeoutExpired:
        error(f"Antigravity CLI timed out after {timeout}s")
        return None
    except Exception as e:
        error(f"Antigravity CLI execution failed: {e}")
        return None


def _generate_antigravity(
    prompt: str,
    system: str = "",
    timeout: int = 120,
) -> str | None:
    full_prompt = f"{system.strip()}\n\n{prompt.strip()}" if system.strip() else prompt.strip()
    return _run_antigravity_cli(full_prompt, timeout=timeout)


def _chat_antigravity(
    messages: list[dict],
    timeout: int = 180,
) -> dict | None:
    """Format chat messages into a single headless prompt for `agy -p`."""
    system_parts: list[str] = []
    convo_lines: list[str] = []

    for msg in messages:
        role = msg.get("role", "user")
        content = (msg.get("content") or "").strip()
        if not content:
            continue
        if role == "system":
            system_parts.append(content)
        elif role == "assistant":
            convo_lines.append(f"Asistente: {content}")
        else:
            convo_lines.append(f"Usuario: {content}")

    sections: list[str] = []
    if system_parts:
        sections.append("\n".join(system_parts))
    if convo_lines:
        sections.append("Conversación:\n" + "\n".join(convo_lines))
    sections.append("Responde únicamente con el siguiente mensaje del Asistente (sin prefijo 'Asistente:' ni explicaciones de herramientas).")

    reply = _run_antigravity_cli("\n\n".join(sections), timeout=timeout)
    if reply is None:
        return None
    if reply.lower().startswith("asistente:"):
        reply = reply.split(":", 1)[1].strip()
    return {"message": {"content": reply}}


# ── Generate ──────────────────────────────────────────────────

def generate(
    prompt: str,
    model: str = DEFAULT_MODEL,
    system: str = "",
    mode: str = "antigravity",
    api_token: str = "",
    timeout: int = 120,
) -> str | None:
    """
    Generate text using Antigravity CLI (`agy`), local Ollama, or remote DeepSeek API.
    """
    if mode == "antigravity":
        return _generate_antigravity(prompt, system, timeout)
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
        with urllib.request.urlopen(req, timeout=timeout, context=_ssl_context()) as resp:
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
    mode: str = "antigravity",
    api_token: str = "",
    timeout: int = 180,
) -> dict | None:
    """
    Chat completion. Supports Antigravity CLI (`agy`), Ollama, and DeepSeek API.
    Returns dict with {message, content} or None.
    """
    if mode == "antigravity":
        return _chat_antigravity(messages, timeout)
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
        with urllib.request.urlopen(req, timeout=timeout, context=_ssl_context()) as resp:
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
