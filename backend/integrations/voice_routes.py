"""
Voice Routes — REST API endpoints for speech recognition, voice command parsing, and physical pet action dispatch.
"""

from fastapi import APIRouter, File, UploadFile, Request, HTTPException
from pydantic import BaseModel
from integrations.voice_service import VoiceService
from integrations.chat_history import save_message
from services.logger import info, error

router = APIRouter(prefix="/voice", tags=["voice"])

voice_service = VoiceService(language="es-ES")

# Injected by main.py
pet_brain = None
chat_router_module = None


class TextCommandRequest(BaseModel):
    text: str
    session_id: str = "default"


@router.get("/status")
def voice_status():
    """Check voice recognition engine readiness."""
    return {
        "ok": True,
        "service": "SpeechRecognition",
        "engine": "google-es",
        "language": voice_service.language,
    }


@router.post("/transcribe")
async def voice_transcribe(request: Request, file: UploadFile = File(None)):
    """Transcribe raw WAV audio to text."""
    audio_bytes = None
    if file:
        audio_bytes = await file.read()
    else:
        audio_bytes = await request.body()

    if not audio_bytes:
        raise HTTPException(400, "No se recibieron datos de audio")

    text = voice_service.transcribe(audio_bytes)
    if not text:
        return {"ok": False, "text": "", "message": "No se detectó voz clara o hubo silencio"}

    return {"ok": True, "text": text}


@router.post("/command")
async def voice_command(request: Request, file: UploadFile = File(None)):
    """
    Process a voice command:
    1. Transcribes incoming WAV audio.
    2. Checks fast physical intent (ball, ladder, window, snack, jump, sit, etc.).
    3. If matched, immediately dispatches the pet action and saves to chat history.
    4. If conversational, passes to the AI chat engine to respond and act.
    """
    audio_bytes = None
    if file:
        audio_bytes = await file.read()
    else:
        # Check if content-type is audio or json
        content_type = request.headers.get("content-type", "")
        if "application/json" in content_type:
            try:
                data = await request.json()
                text = (data.get("text") or "").strip()
            except Exception:
                text = ""
            if not text:
                raise HTTPException(400, "Campo 'text' requerido")
            return await _process_voice_text(text)
        else:
            audio_bytes = await request.body()

    if not audio_bytes or len(audio_bytes) < 44:
        raise HTTPException(400, "Audio no válido o vacío")

    text = voice_service.transcribe(audio_bytes)
    if not text:
        return {
            "ok": False,
            "text": "",
            "response": "No pude entender lo que dijiste 🐾 ¿Puedes repetirlo?",
            "action": None,
        }

    return await _process_voice_text(text)


async def _process_voice_text(text: str) -> dict:
    """Evaluate text, match direct physical actions, or forward to AI chat."""
    info(f"[VoiceCommand] Processing text: '{text}'")

    # 1. Check direct physical intent
    intent = voice_service.match_intent(text)

    if intent:
        # Save to chat history
        save_message("default", "user", f"🎙️ {text}")
        save_message("default", "assistant", intent.get("speech") or "¡Entendido! 🐾")

        # Dispatch physical action to desktop pet
        dispatched = None
        if pet_brain:
            try:
                dispatched = pet_brain.dispatch_action(intent)
            except Exception as e:
                error(f"[VoiceCommand] Failed to dispatch action: {e}")

        return {
            "ok": True,
            "text": text,
            "intent_matched": True,
            "action": intent,
            "response": intent.get("speech"),
            "dispatched": bool(dispatched),
        }

    # 2. Conversational or complex AI request: route through chat_send
    save_message("default", "user", f"🎙️ {text}")
    try:
        from integrations.chat_routes import chat_send, ChatRequest
        from services.config_store import get_ai_mode, get_deepseek_token
        req = ChatRequest(
            message=text,
            session_id="default",
            mode=get_ai_mode() or "antigravity",
            api_token=get_deepseek_token() or "",
        )
        ai_res = chat_send(req)
        response_msg = ai_res.get("response", "¡Te escuché! 🐾") if isinstance(ai_res, dict) else "¡Te escuché! 🐾"
        return {
            "ok": True,
            "text": text,
            "intent_matched": False,
            "action": None,
            "response": response_msg,
        }
    except Exception as e:
        error(f"[VoiceCommand] AI chat error: {e}")
        fallback_msg = "¡Te escuché claramente! 🐾"
        save_message("default", "assistant", fallback_msg)
        return {
            "ok": True,
            "text": text,
            "intent_matched": False,
            "action": None,
            "response": fallback_msg,
        }
