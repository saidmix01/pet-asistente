"""
Pet Brain — AI-driven autonomous & interactive behavior controller.

Asks the configured AI (Antigravity CLI, Ollama, or DeepSeek) to decide the
pet's animations, movements across the screen, choreography sequences, sounds,
moods, and contextual speech bubbles.
"""

import json
import re
import threading
import time
from datetime import datetime
from typing import Any

from core.event_stream import EventStream
from core.system_state import SystemState
from services.ai import (
    generate as ai_generate,
    is_antigravity_available,
    is_deepseek_configured,
    is_ollama_available,
)
from services.config_store import (
    get_ai_autonomy,
    get_ai_mode,
    get_assistant_name,
    get_deepseek_token,
)
from services.logger import error, info, warning
from services.pet_memory import get_memory_summary

VALID_ACTIONS = {
    "idle", "idle2", "sit", "walk", "run", "jump",
    "jump_up", "step_up", "jump_down", "step_down", "reset_step",
    "climb_window", "fetch_ball", "feed_snack",
    "sniff", "sniffwalk",
}
VALID_DIRECTIONS = {"left", "right", "keep", "flip"}
VALID_MOODS = {"happy", "focused", "curious", "playful", "sleepy", "alert", "calm"}
VALID_SOUNDS = {"ladrido", "alerta", "ronquido", "none"}
VALID_TARGETS = {"left", "center", "right", None}

BRAIN_SYSTEM_PROMPT = """Eres el cerebro motor y emocional de una mascota virtual (un pug pixel-art) que vive en el escritorio del usuario.
Tu trabajo es decidir cómo se mueve, qué animación hace, a qué parte de la pantalla va, su estado de ánimo, si emite sonido y (opcionalmente) una frase MUY corta en español.

Acciones permitidas (campo "action"):
- "idle" / "idle2": quieto observando o respirando
- "sit": sentarse tranquilo o atento
- "walk": caminar tranquilo
- "run": correr con energía o entusiasmo
- "jump": saltar y subir un escalón en el escritorio quedando elevado
- "jump_up" / "step_up": saltar hacia arriba y quedar sobre un escalón/repisa elevada
- "jump_down" / "step_down": saltar hacia abajo para descender un escalón hacia el suelo
- "reset_step": bajar de todos los escalones de vuelta al suelo de la pantalla
- "climb_window": saltar y trepar sobre la ventana activa del usuario para acompañarlo
- "fetch_ball": correr emocionado a buscar la pelota y traerla de vuelta
- "feed_snack": comer un snack o galleta de código felizmente
- "sniff": olfatear con curiosidad en el sitio
- "sniffwalk": caminar olfateando explorando el escritorio

Campos JSON obligatorios (RESPONDE ÚNICAMENTE CON UN OBJETO JSON VÁLIDO, SIN MARKDOWN NI TEXTO EXTRA):
{
  "action": "walk",
  "direction": "left" | "right" | "flip" | "keep",
  "move_to": "left" | "center" | "right" | null,
  "duration_ms": 2500,
  "mood": "happy" | "focused" | "curious" | "playful" | "sleepy" | "alert" | "calm",
  "sound": "none" | "ladrido" | "alerta" | "ronquido",
  "speech": "Frase corta max 45 caracteres o null si prefiere moverse en silencio",
  "sequence": [
    {"action": "walk", "direction": "right", "duration_ms": 1800},
    {"action": "jump_up", "duration_ms": 1400, "speech": "¡A darle! 🪜"}
  ]
}

Reglas:
- "sequence" es opcional (máx 3 pasos). Úsalo cuando quieras una coreografía natural (ej: caminar y luego sentarse u olfatear).
- No repitas exactamente la misma acción o frase que hiciste recién.
- Usa "sound": "none" la mayoría del tiempo (reserva "ladrido" para entusiasmo/celebración y "ronquido" si está sleepy).
- "speech" puede ser null (~40% de las veces) para que el perrito se vea vivo sin spamear texto todo el rato.
- "duration_ms" entre 1200 y 6000."""


def _extract_json_object(raw: str | None) -> dict[str, Any] | None:
    """Extract the first JSON object from an LLM response string."""
    if not raw:
        return None
    text = raw.strip()
    # Strip markdown code fences if present
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*```$", "", text)
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        pass

    # Fallback: find outermost {...}
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end > start:
        try:
            parsed = json.loads(text[start : end + 1])
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            pass
    return None


def normalize_action(raw: dict[str, Any]) -> dict[str, Any]:
    """Validate and sanitize an AI action payload for safe execution by the renderer."""
    action = str(raw.get("action", "idle")).lower().strip()
    if action not in VALID_ACTIONS:
        action = "idle"

    direction = str(raw.get("direction", "keep")).lower().strip()
    if direction not in VALID_DIRECTIONS:
        direction = "keep"

    move_to = raw.get("move_to")
    if isinstance(move_to, str):
        move_to = move_to.lower().strip()
    if move_to not in VALID_TARGETS:
        move_to = None

    try:
        duration_ms = int(raw.get("duration_ms", 2800))
    except (TypeError, ValueError):
        duration_ms = 2800
    duration_ms = max(1000, min(8000, duration_ms))

    mood = str(raw.get("mood", "calm")).lower().strip()
    if mood not in VALID_MOODS:
        mood = "calm"

    sound = str(raw.get("sound", "none")).lower().strip()
    if sound not in VALID_SOUNDS:
        sound = "none"

    speech = raw.get("speech")
    if isinstance(speech, str):
        speech = speech.strip()
        if not speech or speech.lower() in ("null", "none"):
            speech = None
        else:
            speech = speech[:70]
    else:
        speech = None

    clean_seq: list[dict[str, Any]] = []
    raw_seq = raw.get("sequence")
    if isinstance(raw_seq, list):
        for step in raw_seq[:3]:
            if not isinstance(step, dict):
                continue
            st_action = str(step.get("action", "idle")).lower().strip()
            if st_action not in VALID_ACTIONS:
                continue
            st_dir = str(step.get("direction", "keep")).lower().strip()
            if st_dir not in VALID_DIRECTIONS:
                st_dir = "keep"
            st_move = step.get("move_to")
            if isinstance(st_move, str):
                st_move = st_move.lower().strip()
            if st_move not in VALID_TARGETS:
                st_move = None
            try:
                st_dur = max(800, min(6000, int(step.get("duration_ms", 2000))))
            except (TypeError, ValueError):
                st_dur = 2000
            st_speech = step.get("speech")
            if isinstance(st_speech, str):
                st_speech = st_speech.strip()[:70] or None
            else:
                st_speech = None
            st_sound = str(step.get("sound", "none")).lower().strip()
            if st_sound not in VALID_SOUNDS:
                st_sound = "none"
            clean_seq.append({
                "action": st_action,
                "direction": st_dir,
                "move_to": st_move,
                "duration_ms": st_dur,
                "speech": st_speech,
                "sound": st_sound,
            })

    return {
        "action": action,
        "direction": direction,
        "move_to": move_to,
        "duration_ms": duration_ms,
        "mood": mood,
        "sound": sound,
        "speech": speech,
        "sequence": clean_seq,
        "source": str(raw.get("source", "ai")),
    }


def extract_chat_action(reply_text: str) -> tuple[str, dict[str, Any] | None]:
    """
    Extract an optional `[ACTION: {...}]` tag from a chat response.
    Returns (clean_reply_text, parsed_action_or_None).
    """
    if not reply_text:
        return "", None
    match = re.search(r"\[ACTION:\s*(\{.*?\})\s*\]", reply_text, flags=re.DOTALL | re.IGNORECASE)
    if not match:
        return reply_text.strip(), None

    clean_text = (reply_text[: match.start()] + reply_text[match.end() :]).strip()
    parsed = _extract_json_object(match.group(1))
    if parsed:
        parsed["source"] = "chat"
        return clean_text, normalize_action(parsed)
    return clean_text, None


class PetBrain:
    """
    AI-driven autonomous director for the desktop pet.
    Observes system activity, Pomodoro, time of day, and memories, then asks
    the AI for structured movement/behavior plans and pushes them over WebSocket.
    """

    def __init__(
        self,
        state: SystemState,
        stream: EventStream,
        interval_seconds: float = 50.0,
    ) -> None:
        self._state = state
        self._stream = stream
        self._interval = interval_seconds
        self._running = False
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._thinking = False

        self._mood: str = "calm"
        self._last_action: dict[str, Any] | None = None
        self._recent_actions: list[str] = []
        self._last_decision_ts: float = 0.0
        self._pending_trigger: str | None = None

    def start(self) -> None:
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        info(f"PetBrain AI director started (interval={int(self._interval)}s)")

    def stop(self) -> None:
        self._running = False
        info("PetBrain AI director stopped")

    def notify_event(self, event_name: str) -> None:
        """Hint the brain that a notable event occurred (e.g. activity switch)."""
        self._pending_trigger = event_name

    def get_status(self) -> dict[str, Any]:
        return {
            "autonomy_enabled": get_ai_autonomy(),
            "ai_ready": self._is_ai_ready(),
            "thinking": self._thinking,
            "mood": self._mood,
            "last_action": self._last_action,
            "last_decision_ts": self._last_decision_ts,
        }

    def dispatch_action(self, raw_action: dict[str, Any]) -> dict[str, Any]:
        """Validate, record, and broadcast a `pet.action` event to the desktop pet."""
        action = normalize_action(raw_action)
        prev_mood = self._mood
        self._mood = action["mood"]
        self._last_action = action
        self._recent_actions = (self._recent_actions + [action["action"]])[-5:]

        self._stream.on_event("pet.action", action)
        if prev_mood != self._mood:
            self._stream.on_event("pet.mood", {"mood": self._mood, "previous": prev_mood})

        info(
            f"PetBrain action [{action['source']}]: action={action['action']} "
            f"dir={action['direction']} move_to={action['move_to']} "
            f"mood={action['mood']} seq={len(action['sequence'])}"
        )
        return action

    def decide_now(self, trigger: str = "autonomous", user_hint: str = "") -> dict[str, Any] | None:
        """Ask the AI for the next pet behavior and dispatch it immediately."""
        if not self._is_ai_ready():
            return None
        with self._lock:
            if self._thinking:
                return None
            self._thinking = True

        try:
            mode = get_ai_mode()
            token = get_deepseek_token()
            prompt = self._build_prompt(trigger=trigger, user_hint=user_hint)
            raw = ai_generate(
                prompt=prompt,
                system=BRAIN_SYSTEM_PROMPT,
                mode=mode,
                api_token=token,
                timeout=35,
            )
            parsed = _extract_json_object(raw)
            if not parsed:
                warning(f"PetBrain: AI returned non-JSON response: {(raw or '')[:120]}")
                return None
            parsed["source"] = "command" if user_hint else "ai"
            self._last_decision_ts = time.time()
            return self.dispatch_action(parsed)
        except Exception as e:
            error(f"PetBrain decision failed: {e}")
            return None
        finally:
            with self._lock:
                self._thinking = False

    def _is_ai_ready(self) -> bool:
        mode = get_ai_mode()
        if mode == "antigravity":
            return is_antigravity_available()
        if mode == "local":
            return is_ollama_available()
        if mode == "remote":
            return is_deepseek_configured(get_deepseek_token())
        return False

    def _build_prompt(self, trigger: str, user_hint: str) -> str:
        st = self._state.get_state()
        hour = datetime.now().strftime("%H:%M")
        name = get_assistant_name()

        pomo_info = "inactivo"
        try:
            from integrations.pomodoro import _pomodoro_state
            if _pomodoro_state.get("active"):
                pomo_info = f"activo ({_pomodoro_state.get('phase')})"
        except Exception:
            pass

        mem = ""
        try:
            mem = get_memory_summary(limit=3)
        except Exception:
            pass

        lines = [
            f"Mascota: {name} | Hora local: {hour}",
            f"Actividad del usuario: {st.get('current_activity', 'idle')} | Ventana: {st.get('current_window', 'desconocida')}",
            f"Tiempo de sesión: {int(st.get('session_time', 0) // 60)} min | Productividad: {int(st.get('productivity_score', 0) * 100)}%",
            f"Pomodoro: {pomo_info}",
            f"Tu estado de ánimo actual: {self._mood}",
            f"Tus últimas acciones: {', '.join(self._recent_actions) if self._recent_actions else 'ninguna'}",
            f"Disparador: {trigger}",
        ]
        if mem:
            lines.append(mem)
        if user_hint:
            lines.append(f"ORDEN DIRECTA DEL USUARIO: \"{user_hint}\" — ¡obedece esta orden con el movimiento/animación más acorde!")
        else:
            lines.append("Decide tu próximo movimiento, postura o mini-coreografía natural en el escritorio. Responde SOLO con el JSON.")

        return "\n".join(lines)

    def _loop(self) -> None:
        # Wait until WebSocket loop is up and give startup greeting a few seconds
        while self._running and self._stream._loop is None:
            time.sleep(1)
        time.sleep(8)

        while self._running:
            time.sleep(4)
            if not self._running:
                break
            if not get_ai_autonomy():
                continue
            if not self._stream._clients:
                continue  # Don't burn AI calls when no desktop client is connected
            if not self._is_ai_ready():
                continue

            now = time.time()
            elapsed = now - self._last_decision_ts
            trigger = self._pending_trigger

            if trigger and elapsed >= 18:
                self._pending_trigger = None
                self.decide_now(trigger=trigger)
            elif elapsed >= self._interval:
                self._pending_trigger = None
                self.decide_now(trigger="autonomous")
